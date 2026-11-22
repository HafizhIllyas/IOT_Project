# TFB2093 Internet-of-Things — 2-Minute Video Presentation Script (3 Members)

**Total Duration**: Maximum 2:00 (120 seconds) — **40 seconds per member** (~92–99 spoken words each, **289 spoken words total**).

---

## Recording Checklist (Before Hitting Record)

- Click **`↻ Sync`** in the dashboard header (`http://localhost:8501`) right before recording so the latest hour is live.
- Set the top-right range selector to **`3 days`** and chart parameter to **`Temperature`**.
- Have **Wokwi** already compiled and running in a second browser tab (`hardware/sketch.ino` + `hardware/diagram.json`).
- **Live Values Note**: Live card readings (*Observed now* temperature, *Rain beacon* %, *Latest readings*, and *Tomorrow* outlook) update dynamically with Seri Iskandar's live weather—read whatever number is on your screen if you mention them. Only the **`All`**-window historical statistics below are fixed from our logged dataset (`268` hours / `1,683` forecast records).
- **Hand-offs**: Keep transitions tight—Member 1 ends with *"Now over to [Member 2]"*, and Member 2 ends with *"Over to [Member 3]"*.

---

## Member 1 (0:00 – 0:40) — Problem, Architecture & Data Collection

**[On Screen]**
- **0:00–0:10**: Flash `docs/figures/system_architecture.png` cleanly full-screen.
- **0:10–0:40**: Switch to the live Streamlit dashboard (`3 days` active). Point cursor to the **Header** (highlight **`↻ Sync`**), then **Observed now**, then **Data collection** (`Day 3 of 3`, `72 / 72 h logged`, `SQLite`, `0` missed polls).

> "Hi everyone, we're presenting our Seri Iskandar Weather Monitor for TFB2093. In tropical Perak, rapid afternoon convective storms make forecast verification essential, yet standard weather apps overwrite old predictions. At zero cost—RM 0.00—our Python collector polls Open-Meteo every 15 minutes with automatic retries and Malaysia-time alignment, storing observations and multi-horizon forecasts in SQLite's paired view. We exceeded the 3-day target with 268 continuous hours and 1,683 forecast records—over 11 days logged with zero missed polls—and you can pull fresh readings anytime using Sync. Now over to [Member 2]."

---

## Member 2 (0:40 – 1:20) — Interactive Chart & Statistical Accuracy (Bonus b)

**[On Screen]**
- **0:40–0:55**: Hover across the **Forecast vs observed** chart to show the live tooltip; click **`Humidity`**, then **`Wind speed`**, then back to **`Temperature`**.
- **0:55–1:20**: Click **`All`** in the top-right range bar before quoting the metrics; scroll briefly to show **Forecast accuracy**, the hit-rate callout, and **Error by horizon** bars (`+1 h` to `+24 h`).

> "Thanks. On the interactive chart, solid blue shows observed weather, dashed amber shows forecast, the shaded band highlights error, and the Now line separates history from future predictions. Here, error equals observed minus forecast. Switching to All data, 24-hour temperature MAE is 1.0 degrees Celsius with a +0.7 degree bias, and errors clearly grow from 0.1 at +1 hour to 0.4 at +6 and 1.0 at +24 hours. Rain hit rate jumps from 69% with 27% false alarms at 24 hours to 92% at 6 hours, justifying frequent polling for rain alerts. Over to [Member 3]."

---

## Member 3 (1:20 – 2:00) — Rain Beacon Hardware (Bonus a), Outlook & Cost/Conclusion

**[On Screen]**
- **1:20–1:28**: Point to the dashboard **Rain beacon** card (`3 days` or `All`).
- **1:28–1:46**: Switch to the **Wokwi ESP32 Simulator** tab; press the blue **`TEST MODE`** pushbutton to cycle **Green LED** → **Yellow LED** → **Red LED + Buzzer** while the OLED updates.
- **1:46–2:00**: Switch back to the dashboard and show **Latest readings** and **Tomorrow** cards to close.

> "Thanks. For Bonus (a), our Rain beacon matches our ESP32 firmware's exact next-3-hour Open-Meteo query: green below 40%, amber watch at 40% or 0.1 millimeters, and red alert with buzzer at 70% or 0.5 millimeters. In Wokwi, the ESP32 updates its OLED, LEDs, and buzzer—and pressing TEST MODE cycles every alert state. Back on the dashboard, Latest readings tracks recent hourly errors, and Tomorrow previews high-low temperatures, rain chance, and peak storm window. Built entirely for RM 0.00 versus RM 22.80 in physical parts, our system proves low-cost IoT forecast verification works. Thank you!"
