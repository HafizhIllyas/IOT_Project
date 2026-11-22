# 🌦️ Seri Iskandar Weather Monitor — IoT Forecast Verification & Rain-Alert System

**Course**: TFB2093 Internet-of-Things (Sep 2026) — Universiti Teknologi PETRONAS (UTP)  
**Target Location**: Seri Iskandar, Perak, Malaysia (`Lat: 4.3590° N, Lon: 100.9849° E`, Elevation `36 m`)  
**Total Deployment Cost**: **RM 0.00** (Open-Meteo API + SQLite WAL + Streamlit Community Cloud + Wokwi ESP32 Simulator)

---

## 🚀 Quick Start (Run Locally)

```powershell
# 1. Navigate to the project folder
cd C:\Users\hafiz\.gemini\antigravity\scratch\seri-iskandar-weather-iot

# 2. Sync 5+ continuous days of Seri Iskandar weather & multi-horizon forecasts
py -m src.collector --past-days 5

# 3. Launch the interactive Streamlit Dashboard
py -m streamlit run app.py
```

Run the continuous background collector daemon (polls Open-Meteo every 15 minutes):
```powershell
py -m src.collector --daemon --interval 900
```

Run the automated test suite:
```powershell
py -m unittest discover -s tests -v
```

---

## 🌐 Free Cloud Deployment (Public Submission URL)

1. Push this repository to GitHub.
   - [.github/workflows/hourly_weather_collector.yml](.github/workflows/hourly_weather_collector.yml) runs hourly to keep `data/weather_iot.db` and CSV snapshots updated automatically for free.
2. Open **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub.
3. Click **Create app** → select your repository → set **Main file path** to `app.py` → click **Deploy**.
4. Use the `↻ Sync` button in the top bar anytime to trigger an immediate Open-Meteo sync into SQLite.

---

## 🔌 Bonus (a): Running the Wokwi ESP32 Rain-Indicator Simulator (RM 0.00 Hardware)

All standalone hardware files live in [`hardware/`](./hardware):
- [`hardware/sketch.ino`](./hardware/sketch.ino) — ESP32 firmware connecting to `Wokwi-GUEST` Wi-Fi, querying Open-Meteo (`&forecast_hours=3`) for Seri Iskandar's current + next 3-hour rain risk, and driving an I2C SSD1306 OLED (`0x3C`), Green/Yellow/Red LEDs, and a 2.4 kHz Piezo Buzzer.
- [`hardware/diagram.json`](./hardware/diagram.json) — Complete Wokwi wiring diagram with unobstructed OLED routing.
- [`hardware/libraries.txt`](./hardware/libraries.txt) — Free public Arduino libraries (`ArduinoJson`, `Adafruit GFX Library`, `Adafruit SSD1306`).

**How to run on Wokwi.com**:
1. Open [https://wokwi.com/projects/new/esp32](https://wokwi.com/projects/new/esp32).
2. Paste `hardware/sketch.ino` into the `sketch.ino` tab and `hardware/diagram.json` into `diagram.json`.
3. In **Library Manager** → click `+` → search and add `ArduinoJson`, `Adafruit GFX Library`, and `Adafruit SSD1306` (all free public libraries; do not click *Upload a Library*).
4. Click **Start the simulation**. Press the blue **TEST MODE** button on the breadboard to cycle through **Clear (Green)** → **Watch (Yellow)** → **Imminent Rain (Red + Buzzer)** → **Live API**.

---

## 📁 Project Architecture & Deliverables

| Component | File / Path | Purpose |
| :--- | :--- | :--- |
| **Streamlit Entrypoint** | [`app.py`](./app.py) | Thin Streamlit shell: dark theme header, `↻ Sync` button, `3 days / 24 h / All` selector, MYT auto-refresh. |
| **Dashboard UI Template** | [`assets/dashboard.html`](./assets/dashboard.html) | Self-contained dark UI with interactive SVG chart, Rain Beacon gauge, accuracy table, horizon bars, and Tomorrow outlook. |
| **Analytics Engine** | [`src/analytics.py`](./src/analytics.py) | Single source of truth for MAE/RMSE/Bias (`observed - forecast`), WMO rain verification, Rain Beacon parity, and payload assembly. |
| **Data Collector** | [`src/collector.py`](./src/collector.py) | Open-Meteo client with HTTP retry, MYT timezone alignment, 5-day backfill, and live forward forecasts. |
| **Database Layer** | [`src/database.py`](./src/database.py) | SQLite WAL schema, idempotent upserts, `v_paired_verification` SQL view, and CSV export. |
| **Automated Tests** | [`tests/test_weather_iot.py`](./tests/test_weather_iot.py) | DB-isolated unit & regression tests covering ingestion, metrics, Rain Beacon parity, and UI payload contracts. |
| **Report Generator** | [`generate_report.py`](./generate_report.py) | Dynamically builds `docs/TFB2093_IoT_Project_Report.docx` (Arial 11pt, IEEE 8pt refs, <= 8 pages, rubric on last page). |
| **Submission Packager** | [`package_submission.py`](./package_submission.py) | Creates clean `TFB2093_Seri_Iskandar_Weather_IoT_SourceCode.zip` excluding executables and caches. |
