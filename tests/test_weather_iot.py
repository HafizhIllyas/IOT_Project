"""Unit and regression tests for database, collector, analytics, dashboard payload, and hardware parity."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import pandas as pd

from src.analytics import (
    build_dashboard_payload,
    compute_continuous_metrics,
    compute_rain_verification_metrics,
    evaluate_rain_beacon,
)
from src.collector import parse_open_meteo_payloads
from src.config import BASE_DIR, now_myt
from src.database import (
    export_csv_snapshots,
    init_db,
    load_collection_logs_df,
    load_forecasts_df,
    load_observations_df,
    load_paired_verification_df,
    log_collection_run,
    upsert_forecasts,
    upsert_observations,
)


def _build_mock_open_meteo_payloads() -> tuple[dict, dict]:
    """Build deterministic Open-Meteo Previous-Runs & Live payloads spanning 4 hours (2 past, 2 future)."""
    times = [
        "2026-11-20T19:00",
        "2026-11-20T20:00",  # current hour
        "2026-11-20T21:00",  # +1h future
        "2026-11-20T22:00",  # +2h future
    ]
    prev_data = {
        "hourly": {
            "time": times,
            "temperature_2m": [28.0, 27.0, 26.0, 25.5],
            "temperature_2m_previous_day1": [29.0, 26.0, 24.0, 24.0],  # stale day-old forecast for future
            "temperature_2m_previous_day2": [30.0, 25.5, 23.5, 23.5],
            "relative_humidity_2m": [80.0, 85.0, 88.0, 90.0],
            "relative_humidity_2m_previous_day1": [75.0, 88.0, 82.0, 82.0],
            "relative_humidity_2m_previous_day2": [72.0, 90.0, 80.0, 80.0],
            "precipitation": [0.0, 0.5, 0.0, 0.0],
            "precipitation_previous_day1": [0.0, 0.3, 0.0, 0.0],
            "precipitation_previous_day2": [0.2, 0.1, 0.0, 0.0],
            "wind_speed_10m": [5.0, 4.0, 3.0, 3.0],
            "wind_speed_10m_previous_day1": [6.0, 5.0, 4.0, 4.0],
            "wind_speed_10m_previous_day2": [7.0, 6.0, 4.0, 4.0],
            "precipitation_probability": [10.0, 60.0, 20.0, 20.0],
            "weather_code": [3, 61, 3, 3],
            "apparent_temperature": [30.0, 29.0, 28.0, 27.5],
        }
    }
    live_data = {
        "current": {
            "time": "2026-11-20T20:15",
            "temperature_2m": 27.0,
            "relative_humidity_2m": 85.0,
            "precipitation": 0.5,
            "wind_speed_10m": 4.0,
        },
        "hourly": {
            "time": times,
            "temperature_2m": [28.0, 27.0, 26.8, 26.4],  # live future forecast differs from previous_day1
            "relative_humidity_2m": [80.0, 85.0, 91.0, 93.0],
            "apparent_temperature": [30.0, 29.0, 28.5, 28.0],
            "precipitation_probability": [10.0, 65.0, 82.0, 45.0],
            "precipitation": [0.0, 0.5, 1.8, 0.2],
            "weather_code": [3, 61, 63, 61],
            "wind_speed_10m": [5.0, 4.0, 3.5, 3.2],
        },
    }
    return prev_data, live_data


class WeatherIoTRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test_weather.db"
        self.csv_dir = Path(self._tmp.name) / "csv"
        init_db(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_myt_timezone_helper(self) -> None:
        dt = now_myt()
        self.assertIsNone(dt.tzinfo)
        self.assertGreaterEqual(dt.year, 2026)

    def test_db_schema_idempotent_upsert_and_error_sign_convention(self) -> None:
        prev_data, live_data = _build_mock_open_meteo_payloads()
        obs_rows, fc_rows = parse_open_meteo_payloads(prev_data, live_data, "2026-11-20T20:15")

        # Insert twice to confirm idempotency
        upsert_observations(obs_rows, self.db_path)
        upsert_observations(obs_rows, self.db_path)
        upsert_forecasts(fc_rows, self.db_path)
        upsert_forecasts(fc_rows, self.db_path)

        obs_df = load_observations_df(self.db_path)
        self.assertEqual(len(obs_df), 2)  # Only 19:00 and 20:00 (<= current_hour)

        paired_24 = load_paired_verification_df(horizon_hours=24, db_path=self.db_path)
        self.assertEqual(len(paired_24), 2)
        # 19:00: observed 28.0 - forecast 29.0 = -1.0; 20:00: observed 27.0 - forecast 26.0 = +1.0
        self.assertAlmostEqual(float(paired_24.iloc[0]["err_temp"]), -1.0, places=2)
        self.assertAlmostEqual(float(paired_24.iloc[1]["err_temp"]), 1.0, places=2)

        csvs = export_csv_snapshots(self.db_path, self.csv_dir)
        for csv_path in csvs.values():
            self.assertTrue(csv_path.exists())

    def test_future_forecasts_use_live_api_not_stale_previous_day1(self) -> None:
        """Regression test: future hours must store live Open-Meteo forecast, not previous_day1."""
        prev_data, live_data = _build_mock_open_meteo_payloads()
        _, fc_rows = parse_open_meteo_payloads(prev_data, live_data, "2026-11-20T20:15")
        upsert_forecasts(fc_rows, self.db_path)

        fc_24 = load_forecasts_df(horizon_hours=24, db_path=self.db_path)
        row_21 = fc_24[fc_24["target_timestamp"] == "2026-11-20T21:00"].iloc[0]
        self.assertEqual(row_21["model_source"], "open-meteo-live-api")
        self.assertAlmostEqual(float(row_21["forecast_temp"]), 26.8, places=2)
        self.assertAlmostEqual(float(row_21["forecast_precip_prob"]), 82.0, places=1)

    def test_continuous_and_rain_metrics_accuracy(self) -> None:
        paired = pd.DataFrame(
            [
                {"horizon_hours": 24, "actual_temp": 30.0, "forecast_temp": 29.0, "actual_precipitation": 1.0, "forecast_precipitation": 0.5},
                {"horizon_hours": 24, "actual_temp": 28.0, "forecast_temp": 29.0, "actual_precipitation": 0.0, "forecast_precipitation": 0.4},
                {"horizon_hours": 24, "actual_temp": 26.0, "forecast_temp": 25.0, "actual_precipitation": 0.8, "forecast_precipitation": 0.0},
                {"horizon_hours": 24, "actual_temp": 25.0, "forecast_temp": 25.0, "actual_precipitation": 0.0, "forecast_precipitation": 0.0},
            ]
        )
        m = compute_continuous_metrics(paired, "temp", horizon_hours=24)
        # errors (obs - fcst): +1, -1, +1, 0 -> MAE=0.75, Bias=+0.25
        self.assertAlmostEqual(m["mae"], 0.75, places=3)
        self.assertAlmostEqual(m["mbe"], 0.25, places=3)

        rm = compute_rain_verification_metrics(paired, horizon_hours=24, threshold_mm=0.1)
        self.assertEqual((rm["tp"], rm["fp"], rm["fn"], rm["tn"]), (1, 1, 1, 1))
        self.assertAlmostEqual(rm["pod_recall"], 50.0, places=1)
        self.assertAlmostEqual(rm["far"], 50.0, places=1)

    def test_rain_beacon_3h_window_parity_with_esp32(self) -> None:
        """Regression test: Rain Beacon must inspect exact [0h, +1h, +2h] window & ignore +5h."""
        obs = pd.DataFrame(
            [{"timestamp": "2026-11-20T20:00", "temperature_2m": 28.0, "relative_humidity_2m": 75.0, "precipitation": 0.0}]
        )
        # Clear in [20:00, 21:00, 22:00], heavy storm only at +5h (01:00 next day)
        fc_clear = pd.DataFrame(
            [
                {"target_timestamp": "2026-11-20T20:00", "horizon_hours": 1, "forecast_precipitation": 0.0, "forecast_precip_prob": 10.0, "model_source": "open-meteo-live-api"},
                {"target_timestamp": "2026-11-20T21:00", "horizon_hours": 1, "forecast_precipitation": 0.0, "forecast_precip_prob": 15.0, "model_source": "open-meteo-live-api"},
                {"target_timestamp": "2026-11-20T22:00", "horizon_hours": 24, "forecast_precipitation": 0.0, "forecast_precip_prob": 20.0, "model_source": "open-meteo-live-api"},
                {"target_timestamp": "2026-11-21T01:00", "horizon_hours": 24, "forecast_precipitation": 9.0, "forecast_precip_prob": 98.0, "model_source": "open-meteo-live-api"},
            ]
        )
        res_clear = evaluate_rain_beacon(obs, fc_clear)
        self.assertEqual(res_clear["state"], "GREEN_CLEAR")
        self.assertEqual(res_clear["chance_pct"], 20)

        # Rain at +2h (22:00) must trigger Alert even if multiple horizons exist for 20:00/21:00
        fc_alert = pd.concat(
            [
                fc_clear[fc_clear["target_timestamp"] != "2026-11-20T22:00"],
                pd.DataFrame(
                    [
                        {"target_timestamp": "2026-11-20T20:00", "horizon_hours": 3, "forecast_precipitation": 0.0, "forecast_precip_prob": 10.0, "model_source": "open-meteo-nwp-3h"},
                        {"target_timestamp": "2026-11-20T20:00", "horizon_hours": 6, "forecast_precipitation": 0.0, "forecast_precip_prob": 10.0, "model_source": "open-meteo-nwp-6h"},
                        {"target_timestamp": "2026-11-20T21:00", "horizon_hours": 3, "forecast_precipitation": 0.0, "forecast_precip_prob": 15.0, "model_source": "open-meteo-nwp-3h"},
                        {"target_timestamp": "2026-11-20T22:00", "horizon_hours": 24, "forecast_precipitation": 1.6, "forecast_precip_prob": 85.0, "model_source": "open-meteo-live-api"},
                    ]
                ),
            ],
            ignore_index=True,
        )
        res_alert = evaluate_rain_beacon(obs, fc_alert)
        self.assertEqual(res_alert["state"], "RED_IMMINENT")
        self.assertEqual(res_alert["chance_pct"], 85)

    def test_dashboard_payload_contract_and_strict_json(self) -> None:
        prev_data, live_data = _build_mock_open_meteo_payloads()
        obs_rows, fc_rows = parse_open_meteo_payloads(prev_data, live_data, "2026-11-20T20:15")
        upsert_observations(obs_rows, self.db_path)
        upsert_forecasts(fc_rows, self.db_path)
        log_collection_run("2026-11-20T20:15", "test", len(obs_rows), len(fc_rows), "SUCCESS", 120.0, "", self.db_path)

        payload = build_dashboard_payload(
            load_observations_df(self.db_path),
            load_forecasts_df(db_path=self.db_path),
            load_paired_verification_df(db_path=self.db_path),
            load_collection_logs_df(db_path=self.db_path),
        )
        # Strict JSON serialization rejects NaN/Infinity
        encoded = json.dumps(payload, allow_nan=False)
        self.assertGreater(len(encoded), 200)

        for required_key in (
            "location",
            "coords_label",
            "last_reading_hm",
            "now_obs_temp",
            "now_fc_temp",
            "now_err_temp",
            "rain_beacon",
            "collection",
            "timeline",
            "stats_by_window",
            "latest_readings",
            "tomorrow",
        ):
            self.assertIn(required_key, payload)

        for win in ("24h", "3d", "all"):
            self.assertIn(win, payload["stats_by_window"])
            self.assertEqual(len(payload["stats_by_window"][win]["accuracy_rows"]), 4)
            self.assertIn("temperature", payload["stats_by_window"][win]["horizons"])

    def test_hardware_sketch_and_diagram_regression(self) -> None:
        """Regression test: sketch.ino must query &forecast_hours=3 (not &forecast_days=1)."""
        sketch_text = (BASE_DIR / "hardware" / "sketch.ino").read_text(encoding="utf-8")
        self.assertIn("forecast_hours=3", sketch_text)
        self.assertNotIn("forecast_days=1", sketch_text)

        diagram = json.loads((BASE_DIR / "hardware" / "diagram.json").read_text(encoding="utf-8"))
        part_ids = {p["id"] for p in diagram["parts"]}
        self.assertTrue({"esp", "oled1", "led_green", "led_yellow", "led_red", "bz1", "btn1"}.issubset(part_ids))


if __name__ == "__main__":
    unittest.main()
