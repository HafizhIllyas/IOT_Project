"""
TFB2093 Internet-of-Things Project — Seri Iskandar Weather Monitor
Thin Streamlit shell rendering the dark telemetry & verification dashboard
powered by SQLite + Open-Meteo (with timezone-safe MYT auto-sync and manual Sync).
"""

from __future__ import annotations

import json
from typing import Any
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.analytics import build_dashboard_payload
from src.collector import sync_weather_data
from src.config import ASSETS_DIR, DB_PATH, now_myt
from src.database import (
    init_db,
    load_collection_logs_df,
    load_forecasts_df,
    load_observations_df,
    load_paired_verification_df,
)

DASHBOARD_HTML_PATH = ASSETS_DIR / "dashboard.html"

st.set_page_config(
    page_title="Seri Iskandar Weather Monitor",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], .stApp {
        background-color: #0D1117 !important;
        color: #F0F6FC !important;
    }
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stSidebarCollapsedControl"],
    footer,
    #MainMenu {
        display: none !important;
    }
    .main .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 0.9rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 1252px !important;
        margin: 0 auto !important;
    }
    div[data-testid="stButton"] > button,
    div[data-testid="stButton"] button[kind="secondary"] {
        background-color: #151B23 !important;
        color: #F0F6FC !important;
        border: 1px solid #252C36 !important;
        border-radius: 999px !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        min-height: 31px !important;
        height: 31px !important;
        padding: 0 12px !important;
        line-height: 1 !important;
        white-space: nowrap !important;
        transition: border-color 0.15s ease, background-color 0.15s ease !important;
    }
    div[data-testid="stButton"] > button:hover,
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background-color: #1C222B !important;
        border-color: #58A6FF !important;
        color: #FFFFFF !important;
    }
    div[data-testid="stButton"] > button p {
        font-size: 12px !important;
        margin: 0 !important;
    }
    div[data-testid="stSegmentedControl"] {
        background-color: #151B23 !important;
        border: 1px solid #252C36 !important;
        border-radius: 9px !important;
        padding: 3px !important;
        width: fit-content !important;
        margin-left: auto !important;
    }
    div[data-testid="stSegmentedControl"] [role="radiogroup"] {
        gap: 2px !important;
        flex-wrap: nowrap !important;
    }
    div[data-testid="stSegmentedControl"] button {
        background-color: transparent !important;
        color: #8B949E !important;
        border: 1px solid transparent !important;
        box-shadow: none !important;
        outline: none !important;
        border-radius: 6px !important;
        font-size: 12px !important;
        min-height: 25px !important;
        height: 25px !important;
        padding: 0 9px !important;
        white-space: nowrap !important;
    }
    div[data-testid="stSegmentedControl"] button[aria-checked="true"],
    div[data-testid="stSegmentedControl"] button[data-active="true"] {
        background-color: #28303D !important;
        color: #F0F6FC !important;
        border: 1px solid transparent !important;
        box-shadow: none !important;
        font-weight: 600 !important;
    }
    iframe {
        border: none !important;
        display: block;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=900, show_spinner=False)
def load_cached_dashboard_payload() -> dict[str, Any]:
    """Ensure SQLite contains fresh 3+ day data (in MYT) and assemble UI payload."""
    init_db(DB_PATH)
    obs_df = load_observations_df(DB_PATH)

    should_sync = obs_df.empty or len(obs_df) < 72
    if not obs_df.empty:
        latest_dt = pd.to_datetime(obs_df["timestamp"].max())
        if (pd.Timestamp(now_myt()) - latest_dt) > pd.Timedelta(minutes=75):
            should_sync = True

    if should_sync:
        try:
            sync_weather_data(past_days=5)
        except Exception:
            pass
        obs_df = load_observations_df(DB_PATH)

    fc_df = load_forecasts_df(db_path=DB_PATH)
    paired_df = load_paired_verification_df(db_path=DB_PATH)
    logs_df = load_collection_logs_df(limit=50, db_path=DB_PATH)
    return build_dashboard_payload(obs_df, fc_df, paired_df, logs_df)


def main() -> None:
    payload = load_cached_dashboard_payload()
    if payload.get("empty"):
        st.error("No weather records in SQLite. Run `py -m src.collector --past-days 5` first.")
        st.stop()

    if "win_choice" not in st.session_state:
        st.session_state.win_choice = "3 days"

    hdr_brand, hdr_status, hdr_sync, hdr_win = st.columns(
        [4.75, 2.35, 1.05, 2.35], gap="small", vertical_alignment="center"
    )

    with hdr_brand:
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; gap:12px; padding: 2px 0;">
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
                <circle cx="12.5" cy="11.5" r="5" fill="#F2994A"/>
                <g stroke="#F2994A" stroke-width="1.8" stroke-linecap="round">
                  <line x1="12.5" y1="3.2" x2="12.5" y2="4.9"/>
                  <line x1="12.5" y1="18.1" x2="12.5" y2="19.8"/>
                  <line x1="4.2" y1="11.5" x2="5.9" y2="11.5"/>
                  <line x1="6.6" y1="5.6" x2="7.8" y2="6.8"/>
                  <line x1="17.2" y1="6.8" x2="18.4" y2="5.6"/>
                </g>
                <path d="M11 23.5h12.2a4.3 4.3 0 0 0 .5-8.57 5.8 5.8 0 0 0-11.2-1.45A4.8 4.8 0 0 0 11 23.5Z" fill="#C9D1D9" fill-opacity="0.92"/>
              </svg>
              <div>
                <div style="font-size:18px; font-weight:600; color:#F0F6FC; letter-spacing:-0.015em; line-height:1.2;">{payload['location']}</div>
                <div style="font-size:12.5px; color:#8B949E; margin-top:2px;">{payload['subtitle']}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with hdr_status:
        st.markdown(
            f"""
            <div style="display:flex; justify-content:flex-end;">
              <div style="display:inline-flex; align-items:center; gap:7px; background:#151B23; border:1px solid #252C36; border-radius:999px; padding:6px 13px; font-size:12px; color:#8B949E; white-space:nowrap;">
                <span style="width:7px; height:7px; border-radius:50%; background:#3FB950; box-shadow:0 0 8px rgba(63,185,80,0.75); display:inline-block;"></span>
                <span><strong style="color:#F0F6FC; font-weight:500;">Collecting</strong> &middot; last reading {payload['last_reading_hm']}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with hdr_sync:
        if st.button(
            "↻ Sync",
            key="sync_now_btn",
            use_container_width=True,
            help="Fetch latest Open-Meteo data into SQLite now",
        ):
            try:
                with st.spinner("Syncing..."):
                    res = sync_weather_data(past_days=5)
                load_cached_dashboard_payload.clear()
                st.toast(
                    f"Synced {res['obs_upserted']} observations & {res['forecasts_upserted']} forecasts ({res['latency_ms']} ms)",
                    icon="✅",
                )
                st.rerun()
            except Exception as exc:
                st.toast(f"Sync failed: {exc}", icon="⚠️")

    with hdr_win:
        win_label = st.segmented_control(
            "Range",
            options=["3 days", "24 h", "All"],
            default=st.session_state.win_choice,
            key="win_seg",
            label_visibility="collapsed",
        )
        if win_label:
            st.session_state.win_choice = win_label

    win_code = {"3 days": "3d", "24 h": "24h", "All": "all"}.get(st.session_state.win_choice, "3d")
    template = DASHBOARD_HTML_PATH.read_text(encoding="utf-8")
    rendered_html = (
        template.replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=False))
        .replace("__INITIAL_WIN__", win_code)
    )

    if hasattr(st, "iframe"):
        st.iframe(rendered_html, width="stretch", height="content")
    else:
        components.html(rendered_html, height=1360, scrolling=False)


if __name__ == "__main__":
    main()
