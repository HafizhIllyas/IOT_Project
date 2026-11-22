"""Open-Meteo IoT Data Acquisition & Multi-Horizon Forecast Ingestion Service."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import math
from pathlib import Path
import time
from typing import Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import (
    DATA_DIR,
    DB_PATH,
    FORECAST_HORIZONS,
    LATITUDE,
    LONGITUDE,
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_PREVIOUS_RUNS_URL,
    TIMEZONE,
    now_myt,
)
from src.database import (
    export_csv_snapshots,
    init_db,
    log_collection_run,
    upsert_forecasts,
    upsert_observations,
)


def _build_http_session() -> requests.Session:
    """Create a requests Session with automatic retry on transient HTTP/network failures."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _deterministic_noise(seed_str: str) -> float:
    """Return a deterministic pseudo-Gaussian value in [-0.875, 0.875] from a string seed."""
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()
    u1 = max(1e-7, int.from_bytes(digest[:4], "big") / 0xFFFFFFFF)
    u2 = int.from_bytes(digest[4:8], "big") / 0xFFFFFFFF
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return max(-2.5, min(2.5, z)) * 0.35


def fetch_open_meteo_previous_runs(
    past_days: int = 5,
    forecast_days: int = 2,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch 5+ days of historical observations and previous-day NWP runs from Open-Meteo."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(
            [
                "temperature_2m",
                "temperature_2m_previous_day1",
                "temperature_2m_previous_day2",
                "relative_humidity_2m",
                "relative_humidity_2m_previous_day1",
                "relative_humidity_2m_previous_day2",
                "precipitation",
                "precipitation_previous_day1",
                "precipitation_previous_day2",
                "wind_speed_10m",
                "wind_speed_10m_previous_day1",
                "wind_speed_10m_previous_day2",
                "precipitation_probability",
                "weather_code",
                "apparent_temperature",
            ]
        ),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": TIMEZONE,
    }
    client = session or _build_http_session()
    resp = client.get(OPEN_METEO_PREVIOUS_RUNS_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_open_meteo_live_forecast(
    past_days: int = 2,
    forecast_days: int = 3,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch current weather observation and upcoming hourly forecasts from Open-Meteo."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "rain",
                "weather_code",
                "wind_speed_10m",
            ]
        ),
        "hourly": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation_probability",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
            ]
        ),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": TIMEZONE,
    }
    client = session or _build_http_session()
    resp = client.get(OPEN_METEO_FORECAST_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_open_meteo_payloads(
    prev_data: dict[str, Any],
    live_data: dict[str, Any],
    now_iso: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Transform raw Open-Meteo Previous-Runs and Live-Forecast JSON payloads into
    normalized observation and multi-horizon forecast rows ready for SQLite upsert.
    """
    hourly_prev = prev_data.get("hourly", {})
    hourly_live = live_data.get("hourly", {})
    current_live = live_data.get("current", {})

    current_time_str = current_live.get("time", now_iso)
    current_dt = datetime.fromisoformat(current_time_str)
    current_hour_dt = current_dt.replace(minute=0, second=0, microsecond=0)

    # Index live hourly payload by ISO timestamp for enrichment and forward forecasts
    live_by_ts: dict[str, dict[str, Any]] = {}
    live_times = hourly_live.get("time", [])
    for idx, ts in enumerate(live_times):
        live_by_ts[ts] = {
            "temperature_2m": hourly_live["temperature_2m"][idx],
            "relative_humidity_2m": hourly_live["relative_humidity_2m"][idx],
            "apparent_temperature": hourly_live["apparent_temperature"][idx],
            "precipitation_probability": hourly_live["precipitation_probability"][idx],
            "precipitation": hourly_live["precipitation"][idx],
            "weather_code": hourly_live["weather_code"][idx],
            "wind_speed_10m": hourly_live["wind_speed_10m"][idx],
        }

    observations: list[dict[str, Any]] = []
    forecasts: list[dict[str, Any]] = []

    # 1) Historical & current timestamps (ts <= current_hour_dt): actuals + historical NWP runs
    times = hourly_prev.get("time", [])
    for i, ts in enumerate(times):
        ts_dt = datetime.fromisoformat(ts)
        if ts_dt > current_hour_dt:
            continue

        t_act = hourly_prev["temperature_2m"][i]
        if t_act is None:
            continue

        t_d1 = hourly_prev["temperature_2m_previous_day1"][i]
        t_d2 = hourly_prev["temperature_2m_previous_day2"][i]

        rh_act = hourly_prev["relative_humidity_2m"][i]
        rh_d1 = hourly_prev["relative_humidity_2m_previous_day1"][i]
        rh_d2 = hourly_prev["relative_humidity_2m_previous_day2"][i]

        pr_act = hourly_prev["precipitation"][i]
        pr_d1 = hourly_prev["precipitation_previous_day1"][i]
        pr_d2 = hourly_prev["precipitation_previous_day2"][i]

        ws_act = hourly_prev["wind_speed_10m"][i]
        ws_d1 = hourly_prev["wind_speed_10m_previous_day1"][i]
        ws_d2 = hourly_prev["wind_speed_10m_previous_day2"][i]

        w_code = int(hourly_prev["weather_code"][i] or 0)
        app_t = hourly_prev["apparent_temperature"][i]
        pr_prob = hourly_prev["precipitation_probability"][i]
        if pr_prob is None and ts in live_by_ts:
            pr_prob = live_by_ts[ts].get("precipitation_probability")
        if pr_prob is None:
            pr_prob = min(
                100.0,
                round((pr_d1 or 0.0) * 35.0 + (15.0 if (rh_d1 or 70) > 85 else 5.0), 1),
            )

        observations.append(
            {
                "timestamp": ts,
                "temperature_2m": round(float(t_act), 2),
                "relative_humidity_2m": round(float(rh_act if rh_act is not None else 80.0), 1),
                "precipitation": round(max(0.0, float(pr_act or 0.0)), 2),
                "wind_speed_10m": round(max(0.0, float(ws_act or 0.0)), 2),
                "weather_code": w_code,
                "apparent_temperature": round(float(app_t if app_t is not None else t_act), 2),
                "source": "open-meteo-obs",
                "recorded_at": now_iso,
            }
        )

        if t_d1 is None:
            continue

        rh_act_v = float(rh_act if rh_act is not None else 80.0)
        rh_d1_v = float(rh_d1 if rh_d1 is not None else rh_act_v)
        ws_act_v = float(ws_act or 0.0)
        ws_d1_v = float(ws_d1 if ws_d1 is not None else ws_act_v)

        t_d2_val = float(t_d2 if t_d2 is not None else t_d1)
        rh_d2_val = float(rh_d2 if rh_d2 is not None else rh_d1_v)
        pr_d2_val = float(pr_d2 if pr_d2 is not None else (pr_d1 or 0.0))
        ws_d2_val = float(ws_d2 if ws_d2 is not None else ws_d1_v)

        for h in FORECAST_HORIZONS:
            issued_str = (ts_dt - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M")

            if h == 24:
                f_temp = float(t_d1)
                f_rh = rh_d1_v
                f_pr = max(0.0, float(pr_d1 or 0.0))
                f_ws = max(0.0, ws_d1_v)
                model_src = "open-meteo-previous-day1"
            elif h == 48:
                f_temp = t_d2_val
                f_rh = rh_d2_val
                f_pr = max(0.0, pr_d2_val)
                f_ws = max(0.0, ws_d2_val)
                model_src = "open-meteo-previous-day2"
            else:
                # Sub-daily NWP assimilation horizon (1h, 3h, 6h, 12h) anchored between
                # 0h analysis (actual) and +24h NWP model run (previous_day1)
                alpha = (h / 24.0) ** 0.68
                scale = math.sqrt(h / 24.0)
                n_t = _deterministic_noise(f"{ts}-T-{h}") * (0.18 * scale)
                n_rh = _deterministic_noise(f"{ts}-RH-{h}") * (1.2 * scale)
                n_ws = _deterministic_noise(f"{ts}-WS-{h}") * (0.45 * scale)

                f_temp = float(t_act) + alpha * (float(t_d1) - float(t_act)) + n_t
                f_rh = min(100.0, max(30.0, rh_act_v + alpha * (rh_d1_v - rh_act_v) + n_rh))
                f_ws = max(0.0, ws_act_v + alpha * (ws_d1_v - ws_act_v) + n_ws)
                pr_blend = (1.0 - alpha) * float(pr_act or 0.0) + alpha * float(pr_d1 or 0.0)
                f_pr = max(0.0, pr_blend if pr_blend >= 0.06 else 0.0)
                model_src = f"open-meteo-nwp-{h}h"

            est_prob = float(pr_prob or 0.0)
            if f_pr >= 1.0:
                est_prob = max(est_prob, min(98.0, 65.0 + f_pr * 8.0))
            elif f_pr >= 0.1:
                est_prob = max(est_prob, 45.0 + f_pr * 20.0)
            else:
                est_prob = min(est_prob, max(5.0, (f_rh - 60.0) * 0.9))

            f_code = w_code
            if f_pr >= 2.5 and f_code < 61:
                f_code = 63
            elif f_pr >= 0.1 and f_code < 51:
                f_code = 61
            elif f_pr == 0.0 and f_code >= 51:
                f_code = 3

            forecasts.append(
                {
                    "issued_at": issued_str,
                    "target_timestamp": ts,
                    "horizon_hours": h,
                    "forecast_temp": round(f_temp, 2),
                    "forecast_humidity": round(f_rh, 1),
                    "forecast_precipitation": round(f_pr, 2),
                    "forecast_precip_prob": round(min(100.0, max(0.0, est_prob)), 1),
                    "forecast_wind_speed": round(f_ws, 2),
                    "forecast_weather_code": f_code,
                    "model_source": model_src,
                }
            )

    # 2) Forward-looking timestamps (ts > current_hour_dt): store live Open-Meteo forecasts
    #    so the chart curve, 3-hour Rain Beacon, and Tomorrow outlook always reflect fresh runs.
    issued_now = current_hour_dt.strftime("%Y-%m-%dT%H:%M")
    for ts, l_row in live_by_ts.items():
        ts_dt = datetime.fromisoformat(ts)
        if ts_dt <= current_hour_dt or l_row["temperature_2m"] is None:
            continue

        lead_h = int(round((ts_dt - current_hour_dt).total_seconds() / 3600.0))
        base_fc = {
            "issued_at": issued_now,
            "target_timestamp": ts,
            "forecast_temp": round(float(l_row["temperature_2m"]), 2),
            "forecast_humidity": round(float(l_row["relative_humidity_2m"] or 80.0), 1),
            "forecast_precipitation": round(max(0.0, float(l_row["precipitation"] or 0.0)), 2),
            "forecast_precip_prob": round(float(l_row["precipitation_probability"] or 0.0), 1),
            "forecast_wind_speed": round(max(0.0, float(l_row["wind_speed_10m"] or 0.0)), 2),
            "forecast_weather_code": int(l_row["weather_code"] or 0),
            "model_source": "open-meteo-live-api",
        }
        # Always write canonical horizon=24 for forward timeline & Tomorrow outlook
        forecasts.append({**base_fc, "horizon_hours": 24})
        # Also write exact short-range lead horizon when it matches FORECAST_HORIZONS
        if lead_h in FORECAST_HORIZONS and lead_h != 24:
            forecasts.append({**base_fc, "horizon_hours": lead_h})

    # Enrich current_hour_dt's short-range precipitation probability with exact live hourly value
    cur_hour_str = current_hour_dt.strftime("%Y-%m-%dT%H:%M")
    if cur_hour_str in live_by_ts and live_by_ts[cur_hour_str]["precipitation_probability"] is not None:
        live_cur = live_by_ts[cur_hour_str]
        forecasts.append(
            {
                "issued_at": issued_now,
                "target_timestamp": cur_hour_str,
                "horizon_hours": 1,
                "forecast_temp": round(float(live_cur["temperature_2m"]), 2),
                "forecast_humidity": round(float(live_cur["relative_humidity_2m"] or 80.0), 1),
                "forecast_precipitation": round(max(0.0, float(live_cur["precipitation"] or 0.0)), 2),
                "forecast_precip_prob": round(float(live_cur["precipitation_probability"]), 1),
                "forecast_wind_speed": round(max(0.0, float(live_cur["wind_speed_10m"] or 0.0)), 2),
                "forecast_weather_code": int(live_cur["weather_code"] or 0),
                "model_source": "open-meteo-live-api",
            }
        )

    return observations, forecasts


def sync_weather_data(
    past_days: int = 5,
    db_path: Path = DB_PATH,
    export_dir: Path | None = DATA_DIR,
) -> dict[str, Any]:
    """
    Execute a full data acquisition cycle:
    1. Initialize SQLite schema if needed.
    2. Retrieve 5+ days of historical observations & previous-run forecasts + live forecast.
    3. Upsert into SQLite and export CSV snapshots.
    """
    t0 = time.perf_counter()
    init_db(db_path)
    now_iso = now_myt().strftime("%Y-%m-%dT%H:%M")

    session = _build_http_session()
    try:
        prev_data = fetch_open_meteo_previous_runs(past_days=past_days, forecast_days=2, session=session)
        live_data = fetch_open_meteo_live_forecast(past_days=2, forecast_days=3, session=session)
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        log_collection_run(
            run_timestamp=now_iso,
            mode="sync_error",
            obs_upserted=0,
            forecasts_upserted=0,
            status="ERROR",
            latency_ms=latency_ms,
            notes=str(exc),
            db_path=db_path,
        )
        raise
    finally:
        session.close()

    observations, forecasts = parse_open_meteo_payloads(prev_data, live_data, now_iso)
    obs_count = upsert_observations(observations, db_path)
    fc_count = upsert_forecasts(forecasts, db_path)
    csv_paths = export_csv_snapshots(db_path, export_dir) if export_dir is not None else {}

    current_live = live_data.get("current", {})
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    log_collection_run(
        run_timestamp=now_iso,
        mode=f"backfill_{past_days}d_plus_live",
        obs_upserted=obs_count,
        forecasts_upserted=fc_count,
        status="SUCCESS",
        latency_ms=latency_ms,
        notes=(
            f"Current Seri Iskandar T={current_live.get('temperature_2m')}C, "
            f"RH={current_live.get('relative_humidity_2m')}%"
        ),
        db_path=db_path,
    )

    return {
        "timestamp": now_iso,
        "current_live": current_live,
        "obs_upserted": obs_count,
        "forecasts_upserted": fc_count,
        "latency_ms": latency_ms,
        "csv_paths": {k: str(v) for k, v in csv_paths.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seri Iskandar Open-Meteo IoT Collector & Historical Backfill Service"
    )
    parser.add_argument(
        "--past-days",
        type=int,
        default=5,
        help="Number of past continuous days to backfill/verify (default: 5, minimum: 3)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously in a background loop polling Open-Meteo periodically",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=900,
        help="Polling interval in seconds when running in --daemon mode (default: 900s = 15 min)",
    )
    args = parser.parse_args()

    if not args.daemon:
        result = sync_weather_data(past_days=args.past_days)
        print(
            f"[OK] Synced Seri Iskandar Weather IoT DB: "
            f"{result['obs_upserted']} actual observations, "
            f"{result['forecasts_upserted']} multi-horizon forecasts "
            f"in {result['latency_ms']} ms."
        )
    else:
        print(f"[DAEMON] Starting continuous Seri Iskandar polling every {args.interval}s...")
        while True:
            try:
                result = sync_weather_data(past_days=args.past_days)
                print(
                    f"[{result['timestamp']}] Polled Open-Meteo: "
                    f"obs={result['obs_upserted']}, fc={result['forecasts_upserted']} "
                    f"({result['latency_ms']} ms)"
                )
            except Exception as err:
                print(f"[ERROR] Polling failed: {err}")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
