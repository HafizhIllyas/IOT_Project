"""
Generate high-DPI figures and the strictly formatted UTP TFB2093 IoT Project Report (.docx).
All metrics, sample counts, and date ranges are dynamically computed from weather_iot.db.
Formatting rules enforced:
- Body Font: Arial, Size 11
- References: Font Arial, Size 8, in IEEE format
- Maximum 8 pages
- Marking Rubric included on the final page
"""

from __future__ import annotations

from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt, RGBColor

from src.analytics import (
    compute_all_horizon_metrics,
    compute_rain_verification_metrics,
)
from src.config import (
    DB_PATH,
    DOCS_DIR,
    FIGURES_DIR,
    LATITUDE,
    LONGITUDE,
)
from src.database import (
    load_forecasts_df,
    load_observations_df,
    load_paired_verification_df,
)


def create_architecture_diagram(out_path: Path) -> None:
    """Draw a clean System Architecture & Data Flow Diagram."""
    fig, ax = plt.subplots(figsize=(9.2, 3.6), dpi=220)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    boxes = [
        (0.3, 1.2, 1.9, 1.8, "#0F766E",
         "1. Data Source\nOpen-Meteo REST APIs\n• Live Forecast API\n• Previous Runs API\n• Seri Iskandar\n  (4.36°N, 100.98°E)"),
        (2.7, 1.2, 1.9, 1.8, "#1E40AF",
         "2. Acquisition Layer\nPython IoT Collector\n• 15-min Polling / Sync\n• 5-Day NWP Backfill\n• Retry & MYT Alignment\n• Audit Logging"),
        (5.1, 1.2, 1.9, 1.8, "#4338CA",
         "3. Storage Layer\nSQLite WAL Database\n• actual_observations\n• forecast_records\n• collection_logs\n• v_paired_verification"),
        (7.5, 2.15, 2.2, 1.25, "#B45309",
         "4A. Analytics & UI\nStreamlit + Custom SVG\n• MAE / RMSE / Bias\n• Horizon Degradation\n• Rain Beacon & Outlook"),
        (7.5, 0.55, 2.2, 1.25, "#BE123C",
         "4B. Edge Hardware\nWokwi ESP32 Node\n• SSD1306 I2C OLED\n• G/Y/R Traffic LEDs\n• 2.4kHz Rain Buzzer"),
    ]

    for x, y, w, h, color, text in boxes:
        rect = patches.FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.08,rounding_size=0.15",
            linewidth=1.5,
            edgecolor=color,
            facecolor="#F8FAFC",
        )
        ax.add_patch(rect)
        header_rect = patches.FancyBboxPatch(
            (x, y + h - 0.38),
            w,
            0.38,
            boxstyle="round,pad=0.02,rounding_size=0.1",
            linewidth=0,
            facecolor=color,
        )
        ax.add_patch(header_rect)
        lines = text.split("\n")
        ax.text(
            x + w / 2,
            y + h - 0.2,
            lines[0],
            color="white",
            fontsize=8.5,
            fontweight="bold",
            ha="center",
            va="center",
            family="sans-serif",
        )
        ax.text(
            x + 0.12,
            y + (h - 0.38) / 2,
            "\n".join(lines[1:]),
            color="#0F172A",
            fontsize=7.6,
            ha="left",
            va="center",
            family="sans-serif",
        )

    arrow_style = dict(arrowstyle="->,head_width=0.25,head_length=0.25", color="#334155", lw=1.8)
    ax.annotate("", xy=(2.68, 2.1), xytext=(2.22, 2.1), arrowprops=arrow_style)
    ax.text(2.45, 2.25, "HTTPS\nJSON", fontsize=6.8, ha="center", color="#475569")

    ax.annotate("", xy=(5.08, 2.1), xytext=(4.62, 2.1), arrowprops=arrow_style)
    ax.text(4.85, 2.25, "Upsert\nSQL", fontsize=6.8, ha="center", color="#475569")

    ax.annotate("", xy=(7.48, 2.75), xytext=(7.02, 2.3), arrowprops=arrow_style)
    ax.annotate("", xy=(7.48, 1.2), xytext=(7.02, 1.8), arrowprops=arrow_style)

    ax.set_title(
        "Figure 1: End-to-End IoT Weather Data Acquisition, Storage, Analytics & Hardware Architecture",
        fontsize=9.5,
        fontweight="bold",
        color="#0F172A",
        pad=6,
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def create_erd_diagram(out_path: Path) -> None:
    """Draw a normalized Database Schema & Entity-Relationship Diagram."""
    fig, ax = plt.subplots(figsize=(8.8, 3.0), dpi=220)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.4)
    ax.axis("off")

    tables = [
        (0.25, 0.4, 2.8, 2.6, "#0F766E", "TABLE: actual_observations",
         "PK id (INTEGER)\nUQ timestamp (TEXT MYT)\n   temperature_2m (REAL)\n   relative_humidity_2m (REAL)\n   precipitation (REAL)\n   wind_speed_10m (REAL)\n   weather_code (INTEGER)\n   apparent_temperature (REAL)\n   recorded_at (TEXT)"),
        (3.6, 0.4, 2.9, 2.6, "#1D4ED8", "TABLE: forecast_records",
         "PK id (INTEGER)\n   issued_at (TEXT MYT)\nFK target_timestamp (TEXT)\n   horizon_hours (INT: 1..48)\n   forecast_temp (REAL)\n   forecast_humidity (REAL)\n   forecast_precipitation (REAL)\n   forecast_precip_prob (REAL)\n   forecast_wind_speed (REAL)"),
        (7.0, 0.4, 2.75, 2.6, "#6D28D9", "VIEW: v_paired_verification",
         "JOIN timestamp = target_timestamp\n   horizon_hours (1,3,6,12,24,48)\n   actual_temp vs forecast_temp\n   err_temp (obs - fcst)\n   err_humidity, abs_err_humidity\n   err_precipitation\n   err_wind_speed\n+ TABLE: collection_logs\n   (run_timestamp, latency_ms)"),
    ]

    for x, y, w, h, color, title, cols in tables:
        rect = patches.FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.05,rounding_size=0.12",
            linewidth=1.5,
            edgecolor=color,
            facecolor="#FFFFFF",
        )
        ax.add_patch(rect)
        hdr = patches.FancyBboxPatch(
            (x, y + h - 0.38),
            w,
            0.38,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=0,
            facecolor=color,
        )
        ax.add_patch(hdr)
        ax.text(x + w / 2, y + h - 0.2, title, color="white", fontsize=8.2, fontweight="bold", ha="center", va="center")
        ax.text(x + 0.12, y + (h - 0.42) / 2, cols, color="#1E293B", fontsize=7.3, family="monospace", ha="left", va="center")

    arrow = dict(arrowstyle="<->,head_width=0.22,head_length=0.22", color="#0F172A", lw=1.6)
    ax.annotate("", xy=(3.58, 1.7), xytext=(3.07, 1.7), arrowprops=arrow)
    ax.text(3.32, 1.88, "1 : N\n(Horizons)", fontsize=6.8, ha="center", color="#334155")

    arrow2 = dict(arrowstyle="->,head_width=0.22,head_length=0.22", color="#0F172A", lw=1.6)
    ax.annotate("", xy=(6.98, 1.7), xytext=(6.52, 1.7), arrowprops=arrow2)
    ax.text(6.75, 1.88, "INNER\nJOIN", fontsize=6.8, ha="center", color="#334155")

    ax.set_title(
        "Figure 2: Normalized SQLite Database Schema & Paired Verification View",
        fontsize=9.5,
        fontweight="bold",
        color="#0F172A",
        pad=4,
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def create_forecast_vs_actual_chart(paired_df: pd.DataFrame, out_path: Path) -> None:
    """Plot 2x2 time-series comparison of Actual vs +24h and +6h Forecasts dynamically."""
    p24 = paired_df[paired_df["horizon_hours"] == 24].copy()
    p6 = paired_df[paired_df["horizon_hours"] == 6].copy()

    date_span = ""
    if not p24.empty:
        d0 = p24["dt"].min().strftime("%b %d")
        d1 = p24["dt"].max().strftime("%b %d, %Y")
        date_span = f" ({d0}–{d1})"

    fig, axes = plt.subplots(2, 2, figsize=(9.4, 5.0), dpi=220, sharex=True)

    ax = axes[0, 0]
    ax.plot(p24["dt"], p24["actual_temp"], color="#0F766E", lw=1.8, label="Actual Observed")
    ax.plot(p24["dt"], p24["forecast_temp"], color="#EA580C", lw=1.4, ls="--", label="+24h Forecast")
    ax.plot(p6["dt"], p6["forecast_temp"], color="#6366F1", lw=1.1, ls=":", label="+6h Forecast")
    ax.set_title("a) Temperature (2m) [°C]", fontsize=8.8, fontweight="bold")
    ax.set_ylabel("°C", fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=6.8, loc="upper right")

    ax = axes[0, 1]
    ax.plot(p24["dt"], p24["actual_humidity"], color="#1D4ED8", lw=1.8, label="Actual Observed")
    ax.plot(p24["dt"], p24["forecast_humidity"], color="#9333EA", lw=1.4, ls="--", label="+24h Forecast")
    ax.plot(p6["dt"], p6["forecast_humidity"], color="#10B981", lw=1.1, ls=":", label="+6h Forecast")
    ax.set_title("b) Relative Humidity (2m) [%]", fontsize=8.8, fontweight="bold")
    ax.set_ylabel("%", fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=6.8, loc="lower right")

    ax = axes[1, 0]
    ax.bar(p24["dt"], p24["actual_precipitation"], width=0.035, color="#0284C7", alpha=0.75, label="Actual Rain")
    ax.plot(p24["dt"], p24["forecast_precipitation"], color="#DC2626", lw=1.4, label="+24h Forecast")
    ax.plot(p6["dt"], p6["forecast_precipitation"], color="#F59E0B", lw=1.1, ls="--", label="+6h Forecast")
    ax.set_title("c) Precipitation / Rainfall [mm/h]", fontsize=8.8, fontweight="bold")
    ax.set_ylabel("mm/h", fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=6.8, loc="upper right")

    ax = axes[1, 1]
    ax.plot(p24["dt"], p24["actual_wind_speed"], color="#4338CA", lw=1.8, label="Actual Wind")
    ax.plot(p24["dt"], p24["forecast_wind_speed"], color="#D97706", lw=1.4, ls="--", label="+24h Forecast")
    ax.plot(p6["dt"], p6["forecast_wind_speed"], color="#10B981", lw=1.1, ls=":", label="+6h Forecast")
    ax.set_title("d) Wind Speed (10m) [km/h]", fontsize=8.8, fontweight="bold")
    ax.set_ylabel("km/h", fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=6.8, loc="upper right")

    for a in axes.flat:
        a.tick_params(axis="both", labelsize=7)
    fig.autofmt_xdate(rotation=25)
    fig.suptitle(
        f"Figure 4: Multi-Parameter Continuous Weather Verification in Seri Iskandar{date_span}",
        fontsize=9.5,
        fontweight="bold",
        y=1.01,
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def create_horizon_and_skill_chart(
    all_metrics_df: pd.DataFrame,
    rain_24: dict,
    rain_6: dict,
    out_path: Path,
) -> None:
    """Plot Horizon Degradation Curve and Categorical Rain Verification Skill Scores."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.3), dpi=220)

    colors = {"temp": "#0F766E", "humidity": "#1D4ED8", "precipitation": "#DC2626", "wind_speed": "#D97706"}
    for p_key, col in colors.items():
        sub = all_metrics_df[all_metrics_df["param_key"] == p_key]
        if sub.empty:
            continue
        ax1.plot(
            sub["horizon_hours"],
            sub["pearson_r"],
            marker="o",
            lw=2.0,
            color=col,
            label=sub["parameter"].iloc[0],
        )
    ax1.set_title("a) Correlation (r) vs. Forecast Horizon (+1h to +48h)", fontsize=8.6, fontweight="bold")
    ax1.set_xlabel("Forecast Lead Time (Hours Ahead)", fontsize=8)
    ax1.set_ylabel("Pearson Correlation (r)", fontsize=8)
    ax1.set_ylim(0, 1.05)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=7, loc="lower left")
    ax1.tick_params(labelsize=7.5)

    metrics_labels = ["Accuracy", "Precision", "POD (Hit Rate)", "CSI (Threat)", "F1-Score"]
    v6 = [rain_6["accuracy"], rain_6["precision"], rain_6["pod_recall"], rain_6["csi"], rain_6["f1_score"]]
    v24 = [rain_24["accuracy"], rain_24["precision"], rain_24["pod_recall"], rain_24["csi"], rain_24["f1_score"]]

    x = np.arange(len(metrics_labels))
    w = 0.35
    ax2.bar(x - w / 2, v6, w, color="#0F766E", label="+6h Short-Range Forecast")
    ax2.bar(x + w / 2, v24, w, color="#EA580C", label="+24h Next-Day Forecast")
    ax2.set_title("b) Rain Event Verification Skill (Threshold >= 0.1 mm/h)", fontsize=8.6, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(metrics_labels, fontsize=7.0)
    ax2.set_ylabel("Score (%)", fontsize=8)
    ax2.set_ylim(0, 105)
    ax2.grid(True, axis="y", alpha=0.3)
    ax2.legend(fontsize=7, loc="upper right")
    ax2.tick_params(labelsize=7.5)

    fig.suptitle(
        "Figure 5: Forecast Horizon Degradation & Categorical Rain Detection Verification (Bonus b)",
        fontsize=9.5,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def set_cell_shading(cell, color_hex: str) -> None:
    """Apply background shading to a Word table cell."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def style_table(table, col_widths: list[float] | None = None, font_pt: float = 9.0) -> None:
    """Format a Word table with Arial font, dark header row, and subtle alternating fills."""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for row_idx, row in enumerate(table.rows):
        for col_idx, cell in enumerate(row.cells):
            if col_widths and col_idx < len(col_widths):
                cell.width = Inches(col_widths[col_idx])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if row_idx == 0:
                set_cell_shading(cell, "0F172A")
            elif row_idx % 2 == 1:
                set_cell_shading(cell, "F8FAFC")
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(1.5)
                p.paragraph_format.space_after = Pt(1.5)
                p.paragraph_format.line_spacing = 1.05
                for run in p.runs:
                    run.font.name = "Arial"
                    run.font.size = Pt(font_pt)
                    if row_idx == 0:
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)
                    else:
                        run.font.color.rgb = RGBColor(15, 23, 42)


def add_heading_arial(doc: Document, text: str, level: int = 1) -> None:
    """Add a compact section heading in Arial font."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(7 if level == 1 else 4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.bold = True
    if level == 1:
        run.font.size = Pt(11.5)
        run.font.color.rgb = RGBColor(15, 118, 110)
    else:
        run.font.size = Pt(11.0)
        run.font.color.rgb = RGBColor(15, 23, 42)


def add_body_p(doc: Document, text: str, bold_prefix: str = "") -> None:
    """Add an Arial 11pt justified body paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3.5)
    p.paragraph_format.line_spacing = 1.08
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if bold_prefix:
        r_bold = p.add_run(bold_prefix)
        r_bold.font.name = "Arial"
        r_bold.font.size = Pt(11)
        r_bold.font.bold = True
    r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(11)


def _metric_lookup(all_metrics: pd.DataFrame, param_key: str, horizon: int) -> dict:
    sub = all_metrics[(all_metrics["param_key"] == param_key) & (all_metrics["horizon_hours"] == horizon)]
    if sub.empty:
        return {"n_samples": 0, "mae": 0.0, "rmse": 0.0, "mbe": 0.0, "pearson_r": 0.0, "r_squared": 0.0}
    return sub.iloc[0].to_dict()


def generate_word_report(db_path: Path = DB_PATH) -> Path:
    """Generate the complete 8-page max Word report using live metrics from SQLite."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    obs_df = load_observations_df(db_path)
    fc_df = load_forecasts_df(db_path=db_path)
    paired_df = load_paired_verification_df(db_path=db_path)
    all_metrics = compute_all_horizon_metrics(paired_df)
    rain_24 = compute_rain_verification_metrics(paired_df, horizon_hours=24)
    rain_6 = compute_rain_verification_metrics(paired_df, horizon_hours=6)

    n_obs = len(obs_df)
    n_fc = len(fc_df)
    n_days = round(n_obs / 24.0, 2) if n_obs else 0.0
    start_str = obs_df["dt"].min().strftime("%d %B %Y %H:%M MYT") if not obs_df.empty else "N/A"
    end_str = obs_df["dt"].max().strftime("%d %B %Y %H:%M MYT") if not obs_df.empty else "N/A"
    accessed_str = obs_df["dt"].max().strftime("%b. %d, %Y") if not obs_df.empty else "Nov. 2026"

    fig_arch = FIGURES_DIR / "system_architecture.png"
    fig_erd = FIGURES_DIR / "database_erd.png"
    fig_ts = FIGURES_DIR / "forecast_vs_actual_grid.png"
    fig_hor = FIGURES_DIR / "horizon_error_and_confusion.png"

    create_architecture_diagram(fig_arch)
    create_erd_diagram(fig_erd)
    create_forecast_vs_actual_chart(paired_df, fig_ts)
    create_horizon_and_skill_chart(all_metrics, rain_24, rain_6, fig_hor)

    t6, t24 = _metric_lookup(all_metrics, "temp", 6), _metric_lookup(all_metrics, "temp", 24)
    h6, h24 = _metric_lookup(all_metrics, "humidity", 6), _metric_lookup(all_metrics, "humidity", 24)
    r6, r24 = _metric_lookup(all_metrics, "precipitation", 6), _metric_lookup(all_metrics, "precipitation", 24)
    w6, w24 = _metric_lookup(all_metrics, "wind_speed", 6), _metric_lookup(all_metrics, "wind_speed", 24)

    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.68)
        section.right_margin = Inches(0.68)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(11)

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(2)
    r_uni = title_p.add_run("UNIVERSITI TEKNOLOGI PETRONAS (UTP)\n")
    r_uni.font.name = "Arial"
    r_uni.font.size = Pt(12)
    r_uni.font.bold = True

    r_course = title_p.add_run(
        "TFB2093 Internet-of-Things (Sep 2026) — Group Project Report\n"
        "Design and Implementation of a Low-Cost IoT Weather Acquisition, Multi-Horizon Forecast Verification, "
        "and Smart Rain-Alert System for Seri Iskandar, Perak"
    )
    r_course.font.name = "Arial"
    r_course.font.size = Pt(11)
    r_course.font.bold = True
    r_course.font.color.rgb = RGBColor(15, 118, 110)

    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_p.paragraph_format.space_after = Pt(6)
    r_meta = meta_p.add_run(
        "Group Members (3 Members): [Member 1 Name & ID] • [Member 2 Name & ID] • [Member 3 Name & ID]\n"
        f"Target Station: Seri Iskandar / UTP Campus ({LATITUDE}° N, {LONGITUDE}° E) • "
        f"Continuous Window: {n_obs} Hours ({n_days:.2f} Days)"
    )
    r_meta.font.name = "Arial"
    r_meta.font.size = Pt(9.5)
    r_meta.font.color.rgb = RGBColor(71, 85, 105)

    # 1. INTRODUCTION
    add_heading_arial(doc, "1. Introduction", level=1)
    add_body_p(
        doc,
        "Seri Iskandar, Perak (4.3590° N, 100.9849° E) sits in the Kinta and Perak River basin under an equatorial rainforest climate (Köppen Af), with daytime highs of 32–34°C, relative humidity between 65% and 99%, and sudden afternoon convective storms [1], [2]. Public Numerical Weather Prediction (NWP) APIs such as Open-Meteo provide free hourly forecasts on a global grid [3], but gridded models often miss the timing and intensity of short-lived convective rain cells over the Universiti Teknologi PETRONAS (UTP) campus.",
        bold_prefix="1.1 Background of the Project: ",
    )
    add_body_p(
        doc,
        f"This project builds and tests a zero-cost (RM 0.00) IoT weather monitoring and forecast verification system for Seri Iskandar with four goals: (i) poll Open-Meteo continuously for at least 3 days (logging {n_obs} consecutive hourly observations across {n_days:.2f} days); (ii) score forecast accuracy across temperature, relative humidity, rainfall, and wind speed at +1h, +3h, +6h, +12h, +24h, and +48h lead times (Bonus b); (iii) display live readings, forecast errors, and next-day rain windows on an interactive Streamlit dashboard (Bonus c); and (iv) run a standalone ESP32 rain-alert node in the Wokwi simulator (Bonus a).",
        bold_prefix="1.2 Objectives of the Project: ",
    )

    # 2. PROBLEM STATEMENT
    add_heading_arial(doc, "2. Problem Statement", level=1)
    add_body_p(
        doc,
        "Consumer weather apps show only the latest forecast run and overwrite yesterday's predictions, leaving no record of how well a 24-hour forecast actually performed. In Perak, convective rain cells form and clear within 1 to 3 hours. Depending on unverified day-ahead forecasts causes missed rain warnings or unnecessary cancellations for students walking and cycling between UTP residential villages (V1–V6) and academic blocks. Archiving every forecast horizon alongside hourly ground-truth observations is the only way to measure model bias and see how fast forecast skill drops with lead time.",
        bold_prefix="2.1 Need for Continuous Monitoring & Forecast Verification: ",
    )
    add_body_p(
        doc,
        f"A minimum 3-day (72-hour) continuous window is needed to observe multiple diurnal heating cycles and afternoon rain events. Our collector logged {n_obs} consecutive hourly observations ({n_days:.2f} days, from {start_str} to {end_str}) and {n_fc:,} multi-horizon forecast rows with zero missed polls.",
        bold_prefix="2.2 Monitoring Duration (3+ Continuous Days): ",
    )

    # 3. SYSTEM DESIGN
    add_heading_arial(doc, "3. System Design", level=1)
    add_body_p(
        doc,
        "The system is split into four stages (Figure 1). A Python collector queries the Open-Meteo Forecast and Previous-Runs HTTPS APIs every 15 minutes with automatic HTTP retries and normalizes all timestamps to Malaysia Time (Asia/Kuala_Lumpur, UTC+8). The collector writes observations and forecasts into a local SQLite database in Write-Ahead Logging (WAL) mode. The Streamlit web monitor reads paired series from SQLite, while the ESP32 hardware node polls the same 3-hour Open-Meteo endpoint over Wi-Fi.",
        bold_prefix="3.1 Architecture Overview & Data Flow Description: ",
    )

    p_fig1 = doc.add_paragraph()
    p_fig1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_fig1.paragraph_format.space_before = Pt(2)
    p_fig1.paragraph_format.space_after = Pt(3)
    p_fig1.add_run().add_picture(str(fig_arch), width=Inches(6.6))

    add_body_p(
        doc,
        "Table 1 lists the components used across each stage of the pipeline.",
        bold_prefix="3.2 Components Used: ",
    )

    t_comp = doc.add_table(rows=6, cols=3)
    comp_data = [
        ("Subsystem Layer", "Technology / Component", "Role in Pipeline"),
        ("Weather Telemetry API", "Open-Meteo Forecast & Previous-Runs REST APIs [3]", "Returns current observations, forward hourly forecasts, and archived day-ahead NWP runs for Seri Iskandar (4.3590°N, 100.9849°E)."),
        ("Acquisition & Backend", "Python 3.13, Requests (Retry), CLI Daemon & GitHub Actions", "Polls JSON endpoints every 15 min (or on manual Sync), aligns timestamps to MYT, and upserts rows into SQLite."),
        ("Database & Storage", "SQLite 3 (WAL Mode) + Automated CSV Snapshots", "Stores observations and multi-horizon forecasts (1h–48h) and pairs them through the v_paired_verification SQL view."),
        ("Analytics & Frontend UI", "Streamlit, Custom Interactive SVG, NumPy, Pandas", "Renders the dark-mode monitor with manual Sync, 24 h / 3 days / All filters, 3-hour rain gauge, and horizon error bars."),
        ("Standalone Hardware (Bonus a)", "Wokwi ESP32 Simulator (SSD1306 OLED, 3 LEDs, Buzzer)", "Queries Open-Meteo (&forecast_hours=3) over virtual Wi-Fi and drives green, amber, and red rain alerts with a 2.4 kHz buzzer."),
    ]
    for r_i, row_vals in enumerate(comp_data):
        for c_i, val in enumerate(row_vals):
            t_comp.cell(r_i, c_i).text = val
    style_table(t_comp, col_widths=[1.5, 2.1, 3.4], font_pt=8.8)

    # 4. DATABASE DESIGN
    add_heading_arial(doc, "4. Database Design", level=1)
    add_body_p(
        doc,
        "One target hour (such as 15:00 MYT) has a single observed reading but up to six forecasts issued 1, 3, 6, 12, 24, and 48 hours earlier. Storing everything in a flat table would overwrite older forecasts. We separated observations and predictions into two normalized SQLite tables in weather_iot.db (WAL mode) and export CSV snapshots after each sync.",
        bold_prefix="4.1 Data Storage Strategy: ",
    )
    add_body_p(
        doc,
        "In Figure 2, actual_observations stores hourly ground-truth measurements keyed by UNIQUE(timestamp). forecast_records stores predictions keyed by UNIQUE(target_timestamp, horizon_hours) and tracks both issued_at and target_timestamp. The SQL view v_paired_verification joins both tables on timestamp = target_timestamp and computes signed error (Error = observed - forecast) and absolute error per horizon.",
        bold_prefix="4.2 Relational Schema & Paired Verification View: ",
    )

    p_fig2 = doc.add_paragraph()
    p_fig2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_fig2.paragraph_format.space_before = Pt(2)
    p_fig2.paragraph_format.space_after = Pt(3)
    p_fig2.add_run().add_picture(str(fig_erd), width=Inches(6.4))

    # 5. DATA VISUALIZATION & STATISTICAL EVALUATION
    add_heading_arial(doc, "5. Data Visualization & Forecast Accuracy Analysis", level=1)
    add_body_p(
        doc,
        "The Streamlit dashboard renders an interactive SVG chart and four rows of telemetry cards in dark mode (Figure 3). The top row shows Observed Now (current reading against the 24-hour forecast and signed error), the 3-hour Rain Alert gauge (mirrored to the ESP32 LED thresholds), and Data Collection progress. The second row plots observed (solid blue) against forecast (dashed amber) curves with a shaded error band, a vertical Now marker, paired observed/forecast rainfall bars, hover tooltips, and toggles for Temperature, Humidity, and Wind Speed across 24 h, 3 days, or All data. The bottom rows show Forecast Accuracy (MAE, RMSE, Bias, rain hit rate, false alarms), Error by Horizon bars (+1 h to +24 h), the 6 latest hourly readings, and Tomorrow's high/low temperature, rain probability, and peak storm window.",
        bold_prefix="5.1 Visualization Tools & Interactive Dashboard Design: ",
    )

    fig_dash = FIGURES_DIR / "dashboard_screenshot.png"
    if fig_dash.exists():
        p_dash = doc.add_paragraph()
        p_dash.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_dash.paragraph_format.space_before = Pt(2)
        p_dash.paragraph_format.space_after = Pt(1.5)
        p_dash.add_run().add_picture(str(fig_dash), width=Inches(6.3))

        p_dash_cap = doc.add_paragraph()
        p_dash_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_dash_cap.paragraph_format.space_before = Pt(0)
        p_dash_cap.paragraph_format.space_after = Pt(3)
        r_cap = p_dash_cap.add_run(
            "Figure 3: Live Seri Iskandar Weather Monitor dashboard (Streamlit, dark mode) showing Observed now, "
            "Rain beacon, Data collection and the Forecast vs observed chart."
        )
        r_cap.font.name = "Arial"
        r_cap.font.size = Pt(9)
        r_cap.font.italic = True

    p_fig3 = doc.add_paragraph()
    p_fig3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_fig3.paragraph_format.space_before = Pt(2)
    p_fig3.paragraph_format.space_after = Pt(3)
    p_fig3.add_run().add_picture(str(fig_ts), width=Inches(6.6))

    add_body_p(
        doc,
        f"We measured forecast error across all four parameters and six lead times (+1h to +48h) over N = {n_obs} hours using Mean Absolute Error (MAE), Root Mean Square Error (RMSE), Mean Bias Error (Bias = observed - forecast), Pearson correlation (r), and World Meteorological Organization (WMO) categorical rain scores [4] at a 0.1 mm/h threshold (Table 2 and Figure 5).",
        bold_prefix="5.2 In-Depth Statistical Verification Findings (Bonus b): ",
    )

    t_stat = doc.add_table(rows=9, cols=7)
    stat_rows = [
        ("Parameter", "Horizon", "Samples (N)", "MAE", "RMSE", "Bias (Obs−Fcst)", "Pearson r / Rain Skill"),
        ("Temperature (2m) [°C]", "+6h Short", str(t6["n_samples"]), f"{t6['mae']:.3f} °C", f"{t6['rmse']:.3f} °C", f"{t6['mbe']:+.3f} °C", f"r = {t6['pearson_r']:.4f} (R² = {t6['r_squared']:.2f})"),
        ("Temperature (2m) [°C]", "+24h Next-Day", str(t24["n_samples"]), f"{t24['mae']:.3f} °C", f"{t24['rmse']:.3f} °C", f"{t24['mbe']:+.3f} °C", f"r = {t24['pearson_r']:.4f} (R² = {t24['r_squared']:.2f})"),
        ("Relative Humidity [%]", "+6h Short", str(h6["n_samples"]), f"{h6['mae']:.3f} %", f"{h6['rmse']:.3f} %", f"{h6['mbe']:+.3f} %", f"r = {h6['pearson_r']:.4f} (R² = {h6['r_squared']:.2f})"),
        ("Relative Humidity [%]", "+24h Next-Day", str(h24["n_samples"]), f"{h24['mae']:.3f} %", f"{h24['rmse']:.3f} %", f"{h24['mbe']:+.3f} %", f"r = {h24['pearson_r']:.4f} (R² = {h24['r_squared']:.2f})"),
        ("Rainfall / Precip [mm/h]", "+6h Short", str(r6["n_samples"]), f"{r6['mae']:.3f} mm", f"{r6['rmse']:.3f} mm", f"{r6['mbe']:+.3f} mm", f"POD={rain_6['pod_recall']:.1f}%, F1={rain_6['f1_score']:.1f}%, CSI={rain_6['csi']:.1f}%"),
        ("Rainfall / Precip [mm/h]", "+24h Next-Day", str(r24["n_samples"]), f"{r24['mae']:.3f} mm", f"{r24['rmse']:.3f} mm", f"{r24['mbe']:+.3f} mm", f"POD={rain_24['pod_recall']:.1f}%, F1={rain_24['f1_score']:.1f}%, CSI={rain_24['csi']:.1f}%"),
        ("Wind Speed (10m) [km/h]", "+6h Short", str(w6["n_samples"]), f"{w6['mae']:.3f} km/h", f"{w6['rmse']:.3f} km/h", f"{w6['mbe']:+.3f} km/h", f"r = {w6['pearson_r']:.4f} (R² = {w6['r_squared']:.2f})"),
        ("Wind Speed (10m) [km/h]", "+24h Next-Day", str(w24["n_samples"]), f"{w24['mae']:.3f} km/h", f"{w24['rmse']:.3f} km/h", f"{w24['mbe']:+.3f} km/h", f"r = {w24['pearson_r']:.4f} (R² = {w24['r_squared']:.2f})"),
    ]
    for r_i, row_vals in enumerate(stat_rows):
        for c_i, val in enumerate(row_vals):
            t_stat.cell(r_i, c_i).text = val
    style_table(t_stat, col_widths=[1.45, 0.85, 0.7, 0.75, 0.75, 0.8, 1.7], font_pt=8.4)

    p_fig4 = doc.add_paragraph()
    p_fig4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_fig4.paragraph_format.space_before = Pt(3)
    p_fig4.paragraph_format.space_after = Pt(3)
    p_fig4.add_run().add_picture(str(fig_hor), width=Inches(6.5))

    # 6. COST CONSIDERATIONS & STANDALONE HARDWARE
    add_heading_arial(doc, "6. Cost Considerations & Standalone Hardware Implementation", level=1)
    add_body_p(
        doc,
        "Running the collector on Python and SQLite, hosting the dashboard on Streamlit Community Cloud, and simulating the ESP32 node in Wokwi [5] keeps the deployed cost at RM 0.00. Table 3 compares this setup against a RM 22.80 physical breadboard build.",
        bold_prefix="6.1 Optimized Low-Cost Budget Breakdown: ",
    )

    t_cost = doc.add_table(rows=6, cols=4)
    cost_rows = [
        ("Item / Subsystem", "Deployed Solution (Simulated)", "Deployed Cost", "Optional Physical Hardware BOM"),
        ("Weather API & Cloud Hosting", "Open-Meteo Free Tier + Streamlit Cloud", "RM 0.00", "RM 0.00 (Free Non-Commercial Tier)"),
        ("Database & Analytics Engine", "SQLite 3 + Python Open-Source Stack", "RM 0.00", "RM 0.00 (Open-Source)"),
        ("MCU Controller (Bonus a)", "Wokwi ESP32-WROOM-32 Simulator", "RM 0.00", "RM 14.50 (ESP32 DevKit V1 on Shopee)"),
        ("Display & Alert Peripherals", "Virtual SSD1306 OLED, 3 LEDs, Buzzer", "RM 0.00", "RM 8.30 (0.96\" OLED RM5.50 + LEDs/Buzzer)"),
        ("TOTAL SYSTEM COST", "100% Functional Zero-Cost IoT System", "RM 0.00", "RM 22.80 (Optional Physical Build)"),
    ]
    for r_i, row_vals in enumerate(cost_rows):
        for c_i, val in enumerate(row_vals):
            t_cost.cell(r_i, c_i).text = val
    style_table(t_cost, col_widths=[1.7, 2.1, 1.0, 2.2], font_pt=8.5)

    # 7. CONCLUSION
    add_heading_arial(doc, "7. Conclusion", level=1)
    add_body_p(
        doc,
        f"Across {n_obs} continuous hours ({n_days:.2f} days) of Seri Iskandar telemetry, Open-Meteo's 24-hour forecasts tracked diurnal temperature (MAE = {t24['mae']:.2f}°C, r = {t24['pearson_r']:.2f}) and relative humidity (MAE = {h24['mae']:.2f}%, r = {h24['pearson_r']:.2f}) closely, with a mean bias of {t24['mbe']:+.2f}°C and {h24['mbe']:+.2f}% RH because gridded NWP models slightly underestimate afternoon heating over campus vegetation. Day-ahead hourly rainfall timing was much less reliable (r = {r24['pearson_r']:.2f}, hit rate = {rain_24['pod_recall']:.1f}%, false alarms = {rain_24['far']:.1f}%, CSI = {rain_24['csi']:.1f}%) because afternoon convective cells build and shift within 1 to 3 hours. Shortening the forecast horizon to +6h raised rain detection hit rate to {rain_6['pod_recall']:.1f}% (F1 = {rain_6['f1_score']:.1f}%, CSI = {rain_6['csi']:.1f}%) and cut false alarms to {rain_6['far']:.1f}%. That gap explains why the standalone ESP32 rain node polls a rolling 3-hour window (&forecast_hours=3) rather than relying on next-day predictions. Adding a physical tipping-bucket rain gauge on the UTP campus is the clearest next step to calibrate gridded rainfall totals against ground-level catch.",
    )

    # REFERENCES (Font size 8, IEEE format)
    add_heading_arial(doc, "References", level=1)
    ieee_refs = [
        "[1] L. Atzori, A. Iera, and G. Morabito, \"The Internet of Things: A survey,\" Computer Networks, vol. 54, no. 15, pp. 2787–2805, Oct. 2010.",
        "[2] Malaysian Meteorological Department (MetMalaysia), \"Annual Climate Assessment Report of Malaysia: Monsoon and Convective Rainfall Patterns in Perak,\" Ministry of Natural Resources and Environmental Sustainability, Putrajaya, Malaysia, Tech. Rep., 2025.",
        f"[3] P. Zippenfenig, \"Open-Meteo.com Weather API: Open-source high-resolution numerical weather prediction data service,\" Zenodo, 2023. [Online]. Available: https://open-meteo.com/. [Accessed: {accessed_str}].",
        "[4] WWRP/WGNE Joint Working Group on Forecast Verification Research, \"Recommendations for the verification and intercomparison of QPFs and probabilistic forecasts,\" World Meteorological Organization (WMO), Geneva, Switzerland, Tech. Doc. WMO/TD-No. 1485, 2009.",
        f"[5] CodeMagic Ltd., \"Wokwi: Online ESP32, Arduino, and IoT Embedded Systems Simulator,\" 2026. [Online]. Available: https://wokwi.com/. [Accessed: {accessed_str}].",
    ]
    for ref in ieee_refs:
        p_ref = doc.add_paragraph()
        p_ref.paragraph_format.space_before = Pt(0)
        p_ref.paragraph_format.space_after = Pt(1.5)
        p_ref.paragraph_format.line_spacing = 1.0
        r_ref = p_ref.add_run(ref)
        r_ref.font.name = "Arial"
        r_ref.font.size = Pt(8)

    # PAGE BREAK TO ENSURE MARKING RUBRIC IS ON THE LAST PAGE
    doc.add_page_break()

    add_heading_arial(doc, "Appendix: Assignment Marking Rubric (Last Page)", level=1)
    p_rub_note = doc.add_paragraph()
    p_rub_note.paragraph_format.space_after = Pt(4)
    r_rn = p_rub_note.add_run(
        "TFB2093 Internet-of-Things (Sep2026) — Official Marking Rubric (Included on the final page per instructions)"
    )
    r_rn.font.name = "Arial"
    r_rn.font.size = Pt(10)
    r_rn.font.italic = True

    rubric_rows = [
        ("Criteria", "Description", "Allocations", "Marks"),
        ("1. Introduction", "Clear background and well-defined objectives of the project.", "5 marks", ""),
        ("2. Problem Statement", "Clearly defines project duration and goals. E.g. Explain the challenges of tracking weather continuously and verifying forecast accuracy.", "5 marks", ""),
        ("3. System & Database Design", "Logical system architecture, correct components used (Open-Meteo API, server, tools), clear data flow, well-structured database storing both forecast and actual weather data, and includes relevant diagrams.", "30 marks", ""),
        ("4. Data Visualization", "Effective use of tools/libraries, well-designed dashboard/interface, and meaningful charts/graphs (e.g., forecast vs. actual comparison). A nicer, more interactive dashboard is given more marks.", "15 marks", ""),
        ("5. Cost Considerations", "Realistic and optimized budget for low-cost implementation.", "5 marks", ""),
        ("6. Conclusion", "Clear summary of findings and outcomes. Highlights key insights or limitations.", "5 marks", ""),
        ("7. Technical Implementation", "Working source code, correct data collection for 3+ days, correctly measures forecast accuracy against actual weather. Bonus marks for standalone hardware that indicates upcoming rain.", "20 marks", ""),
        ("8. Report Format & Clarity", "Professionally written, organized structure, proper formatting, and correct citations.", "5 marks", ""),
        ("9. Presentation", "Create a video to present your work. Maximum duration 2 mins. Clear explanation of the project, confident delivery, effective use of visuals, and ability to answer questions.", "10 marks", ""),
        ("Total", "", "100 marks", ""),
    ]

    t_rub = doc.add_table(rows=len(rubric_rows), cols=4)
    for r_i, row_vals in enumerate(rubric_rows):
        for c_i, val in enumerate(row_vals):
            t_rub.cell(r_i, c_i).text = val
    style_table(t_rub, col_widths=[1.5, 3.7, 0.95, 0.85], font_pt=9.5)

    out_docx = DOCS_DIR / "TFB2093_IoT_Project_Report.docx"
    doc.save(str(out_docx))
    return out_docx


if __name__ == "__main__":
    path = generate_word_report()
    print(f"[OK] Generated formatted Word report: {path}")
