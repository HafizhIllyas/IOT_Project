"""
Single-source-of-truth statistical verification, Rain Beacon logic, and dashboard payload builder.

Unified error convention across SQLite, analytics, dashboard, and report:
    Error = observed - forecast
    Bias (MBE) = mean(observed - forecast)
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from src.config import (
    FORECAST_HORIZONS,
    LATITUDE,
    LONGITUDE,
    RAIN_EVENT_THRESHOLD_MM,
)

PARAMETER_META: dict[str, dict[str, str]] = {
    "temp": {
        "name": "Temperature (2m)",
        "short_name": "Temperature",
        "ui_key": "temperature",
        "unit": "°C",
        "actual_col": "actual_temp",
        "forecast_col": "forecast_temp",
    },
    "humidity": {
        "name": "Relative Humidity (2m)",
        "short_name": "Humidity",
        "ui_key": "humidity",
        "unit": "%",
        "actual_col": "actual_humidity",
        "forecast_col": "forecast_humidity",
    },
    "wind_speed": {
        "name": "Wind Speed (10m)",
        "short_name": "Wind speed",
        "ui_key": "wind_speed",
        "unit": "km/h",
        "actual_col": "actual_wind_speed",
        "forecast_col": "forecast_wind_speed",
    },
    "precipitation": {
        "name": "Precipitation / Rainfall",
        "short_name": "Rainfall",
        "ui_key": "precipitation",
        "unit": "mm",
        "actual_col": "actual_precipitation",
        "forecast_col": "forecast_precipitation",
    },
}

DASHBOARD_HORIZONS = [1, 6, 12, 24]


def compute_continuous_metrics(
    paired_df: pd.DataFrame,
    param_key: str,
    horizon_hours: int = 24,
) -> dict[str, Any]:
    """Compute MAE, RMSE, Bias (observed - forecast), sMAPE, Pearson r, and R^2."""
    meta = PARAMETER_META[param_key]
    sub = paired_df[paired_df["horizon_hours"] == horizon_hours].dropna(
        subset=[meta["actual_col"], meta["forecast_col"]]
    )
    if sub.empty:
        return {
            "parameter": meta["name"],
            "short_name": meta["short_name"],
            "param_key": param_key,
            "unit": meta["unit"],
            "horizon_hours": horizon_hours,
            "n_samples": 0,
            "mae": 0.0,
            "rmse": 0.0,
            "mbe": 0.0,
            "smape": 0.0,
            "pearson_r": 0.0,
            "r_squared": 0.0,
        }

    y_obs = sub[meta["actual_col"]].to_numpy(dtype=float)
    y_fc = sub[meta["forecast_col"]].to_numpy(dtype=float)
    err = y_obs - y_fc  # Error = observed - forecast
    abs_err = np.abs(err)

    mae = float(np.mean(abs_err))
    rmse = float(np.sqrt(np.mean(err**2)))
    mbe = float(np.mean(err))

    denom = (np.abs(y_obs) + np.abs(y_fc)) / 2.0
    valid_smape = denom > 0.05
    smape = float(np.mean(abs_err[valid_smape] / denom[valid_smape]) * 100.0) if np.any(valid_smape) else 0.0

    if len(y_obs) > 2 and np.std(y_obs) > 1e-6 and np.std(y_fc) > 1e-6:
        r_val = float(np.corrcoef(y_obs, y_fc)[0, 1])
    else:
        r_val = 0.0

    return {
        "parameter": meta["name"],
        "short_name": meta["short_name"],
        "param_key": param_key,
        "unit": meta["unit"],
        "horizon_hours": horizon_hours,
        "n_samples": int(len(sub)),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "mbe": round(mbe, 3),
        "smape": round(smape, 2),
        "pearson_r": round(r_val, 4),
        "r_squared": round(r_val**2, 4),
    }


def compute_all_horizon_metrics(paired_df: pd.DataFrame) -> pd.DataFrame:
    """Compute statistical error metrics across all parameters and all forecast horizons."""
    rows = [
        compute_continuous_metrics(paired_df, param_key, h)
        for param_key in PARAMETER_META
        for h in FORECAST_HORIZONS
    ]
    return pd.DataFrame(rows)


def compute_rain_verification_metrics(
    paired_df: pd.DataFrame,
    horizon_hours: int = 24,
    threshold_mm: float = RAIN_EVENT_THRESHOLD_MM,
) -> dict[str, Any]:
    """
    Evaluate binary rain event detection (Rain >= threshold_mm vs Dry) using WMO scores:
    Accuracy, Precision, POD (Hit Rate / Recall), FAR (False Alarm Ratio), CSI, F1, and HSS.
    """
    sub = paired_df[paired_df["horizon_hours"] == horizon_hours].dropna(
        subset=["actual_precipitation", "forecast_precipitation"]
    )
    if sub.empty:
        return {
            "horizon_hours": horizon_hours,
            "threshold_mm": threshold_mm,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "tn": 0,
            "total": 0,
            "accuracy": 0.0,
            "precision": 0.0,
            "pod_recall": 0.0,
            "far": 0.0,
            "csi": 0.0,
            "f1_score": 0.0,
            "hss": 0.0,
        }

    obs_rain = sub["actual_precipitation"].to_numpy(dtype=float) >= threshold_mm
    fc_rain = sub["forecast_precipitation"].to_numpy(dtype=float) >= threshold_mm

    tp = int(np.sum(obs_rain & fc_rain))
    fp = int(np.sum((~obs_rain) & fc_rain))
    fn = int(np.sum(obs_rain & (~fc_rain)))
    tn = int(np.sum((~obs_rain) & (~fc_rain)))
    total = tp + fp + fn + tn

    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    pod_recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    far = fp / (tp + fp) if (tp + fp) > 0 else 0.0
    csi = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0
    f1 = (
        2.0 * precision * pod_recall / (precision + pod_recall)
        if (precision + pod_recall) > 0
        else 0.0
    )
    denom_hss = ((tp + fn) * (fn + tn)) + ((tp + fp) * (fp + tn))
    hss = (2.0 * (tp * tn - fp * fn) / denom_hss) if denom_hss > 0 else 0.0

    return {
        "horizon_hours": horizon_hours,
        "threshold_mm": threshold_mm,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "total": total,
        "accuracy": round(accuracy * 100.0, 2),
        "precision": round(precision * 100.0, 2),
        "pod_recall": round(pod_recall * 100.0, 2),
        "far": round(far * 100.0, 2),
        "csi": round(csi * 100.0, 2),
        "f1_score": round(f1 * 100.0, 2),
        "hss": round(hss, 4),
    }


def evaluate_rain_beacon(
    obs_df: pd.DataFrame,
    fc_df: pd.DataFrame,
) -> dict[str, Any]:
    """
    Evaluate the standalone ESP32 Rain-Indicator Node state (Bonus a) using the exact
    3-hour window [latest_hour, +1h, +2h] matching hardware/sketch.ino (&forecast_hours=3).
    """
    if obs_df.empty:
        return {
            "state": "GREEN_CLEAR",
            "badge": "Clear",
            "color_key": "green",
            "chance_pct": 0,
            "title": "Clear skies ahead",
            "subtitle": "Waiting for first Open-Meteo observation",
            "led_label": "Green LED: low rain probability (< 40%)",
            "current_precip_mm": 0.0,
            "next_3h_max_precip_mm": 0.0,
        }

    latest_obs = obs_df.sort_values("timestamp").iloc[-1]
    latest_dt = pd.to_datetime(latest_obs["timestamp"])
    end_3h_dt = latest_dt + pd.Timedelta(hours=2)
    cur_precip = float(latest_obs["precipitation"])

    # Select exactly one canonical forecast row per hour in [latest_dt, latest_dt + 2h],
    # preferring live Open-Meteo API rows and shortest lead time.
    window_fc = pd.DataFrame()
    if not fc_df.empty:
        fc_work = fc_df.copy()
        if "target_dt" not in fc_work.columns:
            fc_work["target_dt"] = pd.to_datetime(fc_work["target_timestamp"])
        mask = (fc_work["target_dt"] >= latest_dt) & (fc_work["target_dt"] <= end_3h_dt)
        sub = fc_work[mask].copy()
        if not sub.empty:
            sub["_live_rank"] = (sub.get("model_source", "") != "open-meteo-live-api").astype(int)
            window_fc = (
                sub.sort_values(["target_timestamp", "_live_rank", "horizon_hours"])
                .drop_duplicates(subset=["target_timestamp"], keep="first")
                .reset_index(drop=True)
            )

    if not window_fc.empty:
        max_3h_precip = max(cur_precip, float(window_fc["forecast_precipitation"].max()))
        max_3h_prob = float(window_fc["forecast_precip_prob"].max())
    else:
        max_3h_precip = cur_precip
        max_3h_prob = 80.0 if cur_precip >= 0.1 else 15.0

    # Exact parity with hardware/sketch.ino evaluateWeatherAlert()
    if cur_precip >= 0.2 or max_3h_precip >= 0.5 or max_3h_prob >= 70.0:
        state, badge, color_key = "RED_IMMINENT", "Alert", "red"
        title = "Rain imminent"
        led_label = "Red LED: rain imminent or active now"
    elif cur_precip >= 0.05 or max_3h_precip >= 0.1 or max_3h_prob >= 40.0:
        state, badge, color_key = "YELLOW_WATCH", "Watch", "amber"
        title = "Rain likely soon"
        led_label = "Amber LED: rain expected within 2 hours"
    else:
        state, badge, color_key = "GREEN_CLEAR", "Clear", "green"
        title = "Clear skies ahead"
        led_label = "Green LED: low rain probability (< 40%)"

    # Human-readable timing subtitle from upcoming hours
    subtitle = "Next 3 hours look dry (< 0.1 mm/h)"
    if not window_fc.empty:
        rain_rows = window_fc[
            (window_fc["forecast_precipitation"] >= 0.1) | (window_fc["forecast_precip_prob"] >= 40.0)
        ]
        if not rain_rows.empty:
            first_row = rain_rows.iloc[0]
            hours_away = int(round((first_row["target_dt"] - latest_dt).total_seconds() / 3600.0))
            exp_mm = round(max(float(first_row["forecast_precipitation"]), max_3h_precip), 1)
            if hours_away <= 0 and cur_precip >= 0.1:
                subtitle = f"Active rainfall now, peaking around {exp_mm:.1f} mm/h"
            else:
                eta = max(1, hours_away)
                subtitle = f"Expected in about {eta} hour{'s' if eta > 1 else ''}, around {exp_mm:.1f} mm/h"
    elif cur_precip >= 0.1:
        subtitle = f"Active rainfall now ({cur_precip:.1f} mm/h)"

    return {
        "state": state,
        "badge": badge,
        "color_key": color_key,
        "chance_pct": int(round(max_3h_prob)),
        "title": title,
        "subtitle": subtitle,
        "led_label": led_label,
        "current_precip_mm": round(cur_precip, 2),
        "next_3h_max_precip_mm": round(max_3h_precip, 2),
    }


def _compute_window_summary(paired_window: pd.DataFrame) -> dict[str, Any]:
    """Compute Forecast Accuracy table, Rain Skill callout, and Error-by-Horizon bars for one window."""
    table_rows = []
    for key in ("temp", "humidity", "wind_speed", "precipitation"):
        m = compute_continuous_metrics(paired_window, key, horizon_hours=24)
        table_rows.append(
            {
                "name": m["short_name"],
                "unit": f" {m['unit']}",
                "mae": round(m["mae"], 1),
                "rmse": round(m["rmse"], 1),
                "bias": round(m["mbe"], 1),
            }
        )

    rain_m = compute_rain_verification_metrics(paired_window, horizon_hours=24)
    has_rain_events = (rain_m["tp"] + rain_m["fn"]) > 0
    hit_rate_pct = int(round(rain_m["pod_recall"])) if has_rain_events else 100
    false_alarm_pct = int(round(rain_m["far"])) if (rain_m["tp"] + rain_m["fp"]) > 0 else 0

    horizons: dict[str, list[dict[str, Any]]] = {}
    for p_key in ("temp", "humidity", "wind_speed"):
        ui_key = PARAMETER_META[p_key]["ui_key"]
        horizons[ui_key] = [
            {
                "horizon": f"+{h} h",
                "h": h,
                "mae": round(compute_continuous_metrics(paired_window, p_key, h)["mae"], 1),
            }
            for h in DASHBOARD_HORIZONS
        ]

    return {
        "accuracy_rows": table_rows,
        "rain_hit_rate": hit_rate_pct,
        "rain_false_alarm": false_alarm_pct,
        "rain_events": rain_m["tp"] + rain_m["fn"],
        "horizons": horizons,
    }


def build_dashboard_payload(
    obs_df: pd.DataFrame,
    fc_df: pd.DataFrame,
    paired_df: pd.DataFrame,
    logs_df: pd.DataFrame,
) -> dict[str, Any]:
    """Assemble the complete JSON-serializable dashboard payload from DataFrames."""
    if obs_df.empty:
        return {"empty": True}

    obs_sorted = obs_df.sort_values("timestamp").reset_index(drop=True)
    latest_obs = obs_sorted.iloc[-1]
    now_ts = str(latest_obs["timestamp"])
    now_dt = pd.to_datetime(now_ts)

    # Canonical +24h forecast map (historical previous_day1 for past, live forecast for future)
    fc_24 = fc_df[fc_df["horizon_hours"] == 24].copy()
    if fc_24.empty and not fc_df.empty:
        fc_24 = fc_df.drop_duplicates(subset=["target_timestamp"]).copy()
    fc_24_map = fc_24.set_index("target_timestamp").to_dict(orient="index") if not fc_24.empty else {}
    obs_map = obs_sorted.set_index("timestamp").to_dict(orient="index")

    now_obs_temp = float(latest_obs["temperature_2m"])
    now_fc_row = fc_24_map.get(now_ts)
    now_fc_temp = float(now_fc_row["forecast_temp"]) if now_fc_row else now_obs_temp
    now_err_temp = round(now_obs_temp - now_fc_temp, 1)

    missed_polls = int((logs_df["status"] != "SUCCESS").sum()) if (not logs_df.empty and "status" in logs_df.columns) else 0

    # Unified hourly timeline from first observation through end of tomorrow
    tomorrow_dt = (now_dt + pd.Timedelta(days=1)).normalize()
    tomorrow_end_ts = (tomorrow_dt + pd.Timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M")

    all_ts = sorted(
        set(obs_sorted["timestamp"].tolist())
        | {ts for ts in fc_24_map if now_ts < ts <= tomorrow_end_ts}
    )

    timeline: list[dict[str, Any]] = []
    for ts in all_ts:
        dt = pd.to_datetime(ts)
        o_row = obs_map.get(ts)
        f_row = fc_24_map.get(ts)
        is_obs = o_row is not None and ts <= now_ts

        obs_t = round(float(o_row["temperature_2m"]), 1) if is_obs else None
        obs_rh = round(float(o_row["relative_humidity_2m"]), 0) if is_obs else None
        obs_ws = round(float(o_row["wind_speed_10m"]), 1) if is_obs else None
        obs_rain = round(float(o_row["precipitation"]), 2) if is_obs else None

        fc_t = round(float(f_row["forecast_temp"]), 1) if f_row else obs_t
        fc_rh = round(float(f_row["forecast_humidity"]), 0) if f_row else obs_rh
        fc_ws = round(float(f_row["forecast_wind_speed"]), 1) if f_row else obs_ws
        fc_rain = round(float(f_row["forecast_precipitation"]), 2) if f_row else obs_rain

        timeline.append(
            {
                "ts": ts,
                "label": dt.strftime("%a %d %b · %H:%M"),
                "day_label": dt.strftime("%a %d"),
                "hour": int(dt.hour),
                "is_obs": is_obs,
                "obs_temp": obs_t,
                "fc_temp": fc_t,
                "obs_humidity": obs_rh,
                "fc_humidity": fc_rh,
                "obs_wind": obs_ws,
                "fc_wind": fc_ws,
                "obs_rain": obs_rain,
                "fc_rain": fc_rain,
            }
        )

    # Latest 6 hourly readings (most recent first)
    latest_readings = []
    for row in obs_sorted.tail(6).iloc[::-1].itertuples():
        ts_val = str(row.timestamp)
        dt = pd.to_datetime(ts_val)
        f_row = fc_24_map.get(ts_val)
        obs_t = float(row.temperature_2m)
        fc_t = float(f_row["forecast_temp"]) if f_row else obs_t
        latest_readings.append(
            {
                "time": dt.strftime("%a %H:%M"),
                "obs_temp": round(obs_t, 1),
                "fc_temp": round(fc_t, 1),
                "err_temp": round(obs_t - fc_t, 1),
                "humidity": int(round(float(row.relative_humidity_2m))),
                "rain": round(float(row.precipitation), 1),
            }
        )

    # Tomorrow outlook card
    tom_prefix = tomorrow_dt.strftime("%Y-%m-%d")
    tom_fc = fc_24[fc_24["target_timestamp"].str.startswith(tom_prefix)].sort_values("target_timestamp")
    if tom_fc.empty and not fc_df.empty:
        tom_fc = (
            fc_df[fc_df["target_timestamp"].str.startswith(tom_prefix)]
            .drop_duplicates(subset=["target_timestamp"])
            .sort_values("target_timestamp")
        )

    if not tom_fc.empty:
        tom_high = int(round(float(tom_fc["forecast_temp"].max())))
        tom_low = int(round(float(tom_fc["forecast_temp"].min())))
        tom_rain_chance = int(round(float(tom_fc["forecast_precip_prob"].max())))
        tom_rain_sum = round(float(tom_fc["forecast_precipitation"].sum()), 1)

        tom_reset = tom_fc.reset_index(drop=True)
        if tom_rain_sum > 0.1 and len(tom_reset) >= 2:
            peak_idx = int(tom_reset["forecast_precipitation"].rolling(2).sum().fillna(0).idxmax())
        elif len(tom_reset) >= 2:
            peak_idx = int(tom_reset["forecast_temp"].idxmax())
        else:
            peak_idx = 0
        start_idx = max(0, peak_idx - 1)
        end_idx = min(len(tom_reset) - 1, start_idx + 2)
        start_h = pd.to_datetime(tom_reset.iloc[start_idx]["target_timestamp"]).strftime("%H:00")
        end_h = pd.to_datetime(tom_reset.iloc[end_idx]["target_timestamp"]).strftime("%H:00")
        peak_window = f"{start_h} to {end_h}"
    else:
        tom_high, tom_low, tom_rain_chance, tom_rain_sum, peak_window = 32, 24, 50, 2.0, "15:00 to 17:00"

    # Precompute window summaries cleanly via Python analytics (no duplicate math in JS)
    paired_sorted = paired_df.sort_values("timestamp") if not paired_df.empty else paired_df
    cut_24h = (now_dt - pd.Timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M")
    cut_3d = (now_dt - pd.Timedelta(hours=71)).strftime("%Y-%m-%dT%H:%M")

    stats_by_window = {
        "24h": _compute_window_summary(
            paired_sorted[paired_sorted["timestamp"] >= cut_24h] if not paired_sorted.empty else paired_sorted
        ),
        "3d": _compute_window_summary(
            paired_sorted[paired_sorted["timestamp"] >= cut_3d] if not paired_sorted.empty else paired_sorted
        ),
        "all": _compute_window_summary(paired_sorted),
    }

    return {
        "empty": False,
        "location": "Seri Iskandar Weather Monitor",
        "subtitle": "Perak, Malaysia · Open-Meteo forecast vs observed",
        "coords_label": f"{LATITUDE:.4f}°N, {LONGITUDE:.4f}°E",
        "last_reading_hm": now_dt.strftime("%H:%M"),
        "now_ts": now_ts,
        "observed_date_label": now_dt.strftime("%a %d %b"),
        "now_obs_temp": round(now_obs_temp, 1),
        "now_fc_temp": round(now_fc_temp, 1),
        "now_err_temp": now_err_temp,
        "now_humidity": int(round(float(latest_obs["relative_humidity_2m"]))),
        "now_rain": round(float(latest_obs["precipitation"]), 1),
        "now_wind": int(round(float(latest_obs["wind_speed_10m"]))),
        "now_wmo_code": int(latest_obs["weather_code"] or 0),
        "rain_beacon": evaluate_rain_beacon(obs_sorted, fc_df),
        "collection": {
            "total_obs_hours": int(len(obs_sorted)),
            "poll_interval": "15 min",
            "missed_polls": missed_polls,
            "storage": "SQLite",
        },
        "timeline": timeline,
        "stats_by_window": stats_by_window,
        "latest_readings": latest_readings,
        "tomorrow": {
            "date_label": tomorrow_dt.strftime("%a %d %b"),
            "high": tom_high,
            "low": tom_low,
            "rain_chance": tom_rain_chance,
            "expected_rain": tom_rain_sum,
            "peak_window": peak_window,
        },
        "rain_threshold": RAIN_EVENT_THRESHOLD_MM,
    }
