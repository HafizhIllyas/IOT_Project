"""SQLite database management for the Seri Iskandar Weather IoT System."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any
import pandas as pd

from src.config import DATA_DIR, DB_PATH


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Create and configure a SQLite connection in WAL mode."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def db_session(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a transactional SQLite connection and guarantee deterministic closure."""
    conn = get_connection(db_path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    """Initialize normalized database tables and paired verification SQL view."""
    with db_session(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS actual_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT UNIQUE NOT NULL,
                temperature_2m REAL NOT NULL,
                relative_humidity_2m REAL NOT NULL,
                precipitation REAL NOT NULL,
                wind_speed_10m REAL NOT NULL,
                weather_code INTEGER DEFAULT 0,
                apparent_temperature REAL,
                source TEXT DEFAULT 'open-meteo-obs',
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_obs_timestamp
                ON actual_observations(timestamp);

            CREATE TABLE IF NOT EXISTS forecast_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issued_at TEXT NOT NULL,
                target_timestamp TEXT NOT NULL,
                horizon_hours INTEGER NOT NULL,
                forecast_temp REAL NOT NULL,
                forecast_humidity REAL NOT NULL,
                forecast_precipitation REAL NOT NULL,
                forecast_precip_prob REAL DEFAULT 0.0,
                forecast_wind_speed REAL NOT NULL,
                forecast_weather_code INTEGER DEFAULT 0,
                model_source TEXT DEFAULT 'open-meteo-ifs',
                UNIQUE(target_timestamp, horizon_hours)
            );

            CREATE INDEX IF NOT EXISTS idx_fc_target_horizon
                ON forecast_records(target_timestamp, horizon_hours);

            CREATE TABLE IF NOT EXISTS collection_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TEXT NOT NULL,
                mode TEXT NOT NULL,
                obs_upserted INTEGER DEFAULT 0,
                forecasts_upserted INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                latency_ms REAL DEFAULT 0.0,
                notes TEXT
            );

            -- Unified sign convention across DB, analytics, dashboard & report:
            -- Error = observed - forecast
            DROP VIEW IF EXISTS v_paired_verification;
            CREATE VIEW v_paired_verification AS
            SELECT
                o.timestamp AS timestamp,
                f.issued_at AS issued_at,
                f.horizon_hours AS horizon_hours,
                o.temperature_2m AS actual_temp,
                f.forecast_temp AS forecast_temp,
                (o.temperature_2m - f.forecast_temp) AS err_temp,
                ABS(o.temperature_2m - f.forecast_temp) AS abs_err_temp,
                o.relative_humidity_2m AS actual_humidity,
                f.forecast_humidity AS forecast_humidity,
                (o.relative_humidity_2m - f.forecast_humidity) AS err_humidity,
                ABS(o.relative_humidity_2m - f.forecast_humidity) AS abs_err_humidity,
                o.precipitation AS actual_precipitation,
                f.forecast_precipitation AS forecast_precipitation,
                f.forecast_precip_prob AS forecast_precip_prob,
                (o.precipitation - f.forecast_precipitation) AS err_precipitation,
                ABS(o.precipitation - f.forecast_precipitation) AS abs_err_precipitation,
                o.wind_speed_10m AS actual_wind_speed,
                f.forecast_wind_speed AS forecast_wind_speed,
                (o.wind_speed_10m - f.forecast_wind_speed) AS err_wind_speed,
                ABS(o.wind_speed_10m - f.forecast_wind_speed) AS abs_err_wind_speed,
                o.weather_code AS actual_weather_code,
                o.apparent_temperature AS actual_apparent_temp
            FROM actual_observations o
            INNER JOIN forecast_records f
                ON o.timestamp = f.target_timestamp
            ORDER BY o.timestamp ASC, f.horizon_hours ASC;
            """
        )


def upsert_observations(rows: list[dict[str, Any]], db_path: Path = DB_PATH) -> int:
    """Insert or update actual weather observations idempotently."""
    if not rows:
        return 0
    with db_session(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO actual_observations (
                timestamp, temperature_2m, relative_humidity_2m,
                precipitation, wind_speed_10m, weather_code,
                apparent_temperature, source, recorded_at
            ) VALUES (
                :timestamp, :temperature_2m, :relative_humidity_2m,
                :precipitation, :wind_speed_10m, :weather_code,
                :apparent_temperature, :source, :recorded_at
            )
            ON CONFLICT(timestamp) DO UPDATE SET
                temperature_2m = excluded.temperature_2m,
                relative_humidity_2m = excluded.relative_humidity_2m,
                precipitation = excluded.precipitation,
                wind_speed_10m = excluded.wind_speed_10m,
                weather_code = excluded.weather_code,
                apparent_temperature = excluded.apparent_temperature,
                recorded_at = excluded.recorded_at;
            """,
            rows,
        )
    return len(rows)


def upsert_forecasts(rows: list[dict[str, Any]], db_path: Path = DB_PATH) -> int:
    """Insert or update multi-horizon weather forecast records idempotently."""
    if not rows:
        return 0
    with db_session(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO forecast_records (
                issued_at, target_timestamp, horizon_hours,
                forecast_temp, forecast_humidity, forecast_precipitation,
                forecast_precip_prob, forecast_wind_speed,
                forecast_weather_code, model_source
            ) VALUES (
                :issued_at, :target_timestamp, :horizon_hours,
                :forecast_temp, :forecast_humidity, :forecast_precipitation,
                :forecast_precip_prob, :forecast_wind_speed,
                :forecast_weather_code, :model_source
            )
            ON CONFLICT(target_timestamp, horizon_hours) DO UPDATE SET
                issued_at = excluded.issued_at,
                forecast_temp = excluded.forecast_temp,
                forecast_humidity = excluded.forecast_humidity,
                forecast_precipitation = excluded.forecast_precipitation,
                forecast_precip_prob = excluded.forecast_precip_prob,
                forecast_wind_speed = excluded.forecast_wind_speed,
                forecast_weather_code = excluded.forecast_weather_code,
                model_source = excluded.model_source;
            """,
            rows,
        )
    return len(rows)


def log_collection_run(
    run_timestamp: str,
    mode: str,
    obs_upserted: int,
    forecasts_upserted: int,
    status: str,
    latency_ms: float,
    notes: str = "",
    db_path: Path = DB_PATH,
) -> None:
    """Record a data collection execution entry."""
    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT INTO collection_logs (
                run_timestamp, mode, obs_upserted, forecasts_upserted,
                status, latency_ms, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_timestamp,
                mode,
                obs_upserted,
                forecasts_upserted,
                status,
                latency_ms,
                notes,
            ),
        )


def load_observations_df(db_path: Path = DB_PATH) -> pd.DataFrame:
    """Load all actual observations ordered by timestamp."""
    with db_session(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT * FROM actual_observations ORDER BY timestamp ASC", conn
        )
    if not df.empty:
        df["dt"] = pd.to_datetime(df["timestamp"])
    return df


def load_forecasts_df(
    horizon_hours: int | None = None, db_path: Path = DB_PATH
) -> pd.DataFrame:
    """Load forecast records, optionally filtered by horizon_hours."""
    with db_session(db_path) as conn:
        if horizon_hours is not None:
            df = pd.read_sql_query(
                "SELECT * FROM forecast_records WHERE horizon_hours = ? ORDER BY target_timestamp ASC",
                conn,
                params=(horizon_hours,),
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM forecast_records ORDER BY target_timestamp ASC, horizon_hours ASC",
                conn,
            )
    if not df.empty:
        df["target_dt"] = pd.to_datetime(df["target_timestamp"])
    return df


def load_paired_verification_df(
    horizon_hours: int | None = None, db_path: Path = DB_PATH
) -> pd.DataFrame:
    """Load paired actual vs. forecast records from v_paired_verification."""
    with db_session(db_path) as conn:
        if horizon_hours is not None:
            df = pd.read_sql_query(
                "SELECT * FROM v_paired_verification WHERE horizon_hours = ? ORDER BY timestamp ASC",
                conn,
                params=(horizon_hours,),
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM v_paired_verification ORDER BY timestamp ASC, horizon_hours ASC",
                conn,
            )
    if not df.empty:
        df["dt"] = pd.to_datetime(df["timestamp"])
    return df


def load_collection_logs_df(limit: int = 50, db_path: Path = DB_PATH) -> pd.DataFrame:
    """Load recent API ingestion logs."""
    with db_session(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM collection_logs ORDER BY id DESC LIMIT ?",
            conn,
            params=(limit,),
        )


def export_csv_snapshots(
    db_path: Path = DB_PATH,
    out_dir: Path = DATA_DIR,
) -> dict[str, Path]:
    """Export database tables and paired verification view to CSV files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    obs_df = load_observations_df(db_path)
    fc_df = load_forecasts_df(db_path=db_path)
    paired_df = load_paired_verification_df(db_path=db_path)

    obs_csv = out_dir / "seri_iskandar_actual_observations.csv"
    fc_csv = out_dir / "seri_iskandar_forecast_records.csv"
    paired_csv = out_dir / "seri_iskandar_paired_verification.csv"

    if not obs_df.empty:
        obs_df.drop(columns=["dt"], errors="ignore").to_csv(obs_csv, index=False)
    if not fc_df.empty:
        fc_df.drop(columns=["target_dt"], errors="ignore").to_csv(fc_csv, index=False)
    if not paired_df.empty:
        paired_df.drop(columns=["dt"], errors="ignore").to_csv(paired_csv, index=False)

    return {
        "observations_csv": obs_csv,
        "forecasts_csv": fc_csv,
        "paired_csv": paired_csv,
    }
