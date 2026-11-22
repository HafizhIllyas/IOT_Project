"""
Record speech-synchronized 1280x800 H.264 MP4 dashboard walkthrough videos for
Member 1 (0:00-0:43.5) and Member 2 (0:00-0:45.2) against http://localhost:8501.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import time
import imageio_ffmpeg
from playwright.sync_api import FrameLocator, Locator, Page, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = BASE_DIR / "docs" / "recordings"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DASHBOARD_URL = "http://localhost:8501"
VIEWPORT = {"width": 1280, "height": 800}

CURSOR_INIT_JS = """
(() => {
  if (document.getElementById('pw-cursor')) return;
  const el = document.createElement('div');
  el.id = 'pw-cursor';
  Object.assign(el.style, {
    position: 'fixed',
    left: '640px',
    top: '200px',
    width: '18px',
    height: '18px',
    borderRadius: '50%',
    background: 'rgba(88, 166, 255, 0.38)',
    border: '2.5px solid #F0F6FC',
    boxShadow: '0 0 12px rgba(88, 166, 255, 0.9), 0 0 4px rgba(0,0,0,0.8)',
    transform: 'translate(-50%, -50%)',
    pointerEvents: 'none',
    zIndex: '2147483647',
    transition: 'transform 0.08s ease, background 0.12s ease',
  });
  document.documentElement.appendChild(el);
  window.__setPwCursor = (x, y, clicking) => {
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    el.style.transform = clicking
      ? 'translate(-50%, -50%) scale(0.75)'
      : 'translate(-50%, -50%) scale(1)';
    el.style.background = clicking
      ? 'rgba(242, 153, 74, 0.8)'
      : 'rgba(88, 166, 255, 0.38)';
  };
})();
"""


def wait_until(t0: float, target_s: float) -> None:
    """Sleep only if elapsed wall-clock time is behind the scheduled speech cue."""
    rem = target_s - (time.perf_counter() - t0)
    if rem > 0:
        time.sleep(rem)


class DemoChoreographer:
    """Smooth cursor controller tracking both real Playwright mouse and visual overlay."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.cx = 640.0
        self.cy = 200.0
        self.page.evaluate(CURSOR_INIT_JS)

    def ensure_cursor(self) -> None:
        self.page.evaluate(CURSOR_INIT_JS)

    def move_to(self, x: float, y: float, duration_s: float = 0.55, steps: int = 14) -> None:
        self.ensure_cursor()
        start_x, start_y = self.cx, self.cy
        step_dt = max(0.01, duration_s / max(1, steps))
        for i in range(1, steps + 1):
            t = i / steps
            eased = t * t * (3.0 - 2.0 * t)
            nx = start_x + (x - start_x) * eased
            ny = start_y + (y - start_y) * eased
            self.page.mouse.move(nx, ny)
            self.page.evaluate("([x, y]) => window.__setPwCursor && window.__setPwCursor(x, y, false)", [nx, ny])
            time.sleep(step_dt)
        self.cx, self.cy = x, y

    def move_to_locator(
        self,
        loc: Locator,
        duration_s: float = 0.55,
        dx_frac: float = 0.5,
        dy_frac: float = 0.5,
    ) -> tuple[float, float]:
        box = loc.bounding_box()
        if not box:
            raise RuntimeError("Locator bounding_box() returned None")
        tx = box["x"] + box["width"] * dx_frac
        ty = box["y"] + box["height"] * dy_frac
        self.move_to(tx, ty, duration_s=duration_s)
        return tx, ty

    def click_locator(self, loc: Locator, duration_s: float = 0.5) -> None:
        tx, ty = self.move_to_locator(loc, duration_s=duration_s)
        self.page.evaluate("([x, y]) => window.__setPwCursor && window.__setPwCursor(x, y, true)", [tx, ty])
        self.page.mouse.down()
        time.sleep(0.09)
        self.page.mouse.up()
        self.page.evaluate("([x, y]) => window.__setPwCursor && window.__setPwCursor(x, y, false)", [tx, ty])

    def smooth_scroll(self, delta_y: float, duration_s: float = 0.9, steps: int = 18) -> None:
        step_y = delta_y / steps
        step_dt = duration_s / steps
        for _ in range(steps):
            self.page.mouse.wheel(0, step_y)
            time.sleep(step_dt)


def wait_for_dashboard_ready(page: Page) -> FrameLocator:
    """Wait until Streamlit renders the top bar and the inner st.iframe SVG chart."""
    page.wait_for_selector('[data-testid="stButtonGroup"]', timeout=30000)
    page.wait_for_selector("iframe", timeout=30000)
    frame = page.locator("iframe").first.content_frame
    frame.locator("#main-chart-svg polyline").first.wait_for(state="visible", timeout=30000)
    frame.locator("#accuracy-tbody tr").first.wait_for(state="visible", timeout=30000)
    time.sleep(0.7)
    return frame


def sweep_chart_tooltip(
    frame: FrameLocator,
    choreo: DemoChoreographer,
    start_frac: float,
    end_frac: float,
    duration_s: float,
    steps: int = 28,
) -> None:
    """Move cursor smoothly across #chart-hitbox to display live SVG hover tooltips."""
    hitbox = frame.locator("#chart-hitbox")
    box = hitbox.bounding_box()
    if not box:
        return
    y_mid = box["y"] + box["height"] * 0.36
    x0 = box["x"] + box["width"] * start_frac
    x1 = box["x"] + box["width"] * end_frac
    choreo.move_to(x0, y_mid, duration_s=0.45, steps=12)
    choreo.move_to(x1, y_mid, duration_s=duration_s, steps=steps)


def run_member1_sequence(page: Page, frame: FrameLocator, choreo: DemoChoreographer) -> None:
    """
    Synced to Member 1's 43.5s audio:
      0.0-11.5s: Header + Observed now card ("Seri Iskandar Weather Monitor... overwrite predictions")
     11.5-23.0s: Collecting pill -> Poll interval: 15 min -> Storage: SQLite
     23.0-35.0s: Data collection Day 3 of 3, 72 / 72 h logged, Missed polls: 0
     35.0-44.0s: Move to Sync button and hold through hand-off ("...using the Sync function. Now to Amshah.")
    """
    t0 = time.perf_counter()

    # 0.0-11.5s: Opening wide hold -> Header -> Observed now
    wait_until(t0, 2.0)
    choreo.move_to_locator(page.locator("text=Seri Iskandar Weather Monitor").first, duration_s=0.6, dx_frac=0.35)
    wait_until(t0, 5.2)
    choreo.move_to_locator(frame.locator("#now-obs-temp"), duration_s=0.7)
    wait_until(t0, 8.2)
    choreo.move_to_locator(frame.locator("#now-fc-temp"), duration_s=0.5, dy_frac=0.65)
    wait_until(t0, 10.2)
    choreo.move_to_locator(frame.locator("#now-humidity"), duration_s=0.5)

    # 11.5-23.0s: Collecting pill -> Poll interval: 15 min -> Storage: SQLite
    wait_until(t0, 12.0)
    choreo.move_to_locator(page.locator("text=Collecting").first, duration_s=0.65, dx_frac=0.6)
    wait_until(t0, 16.0)
    choreo.move_to_locator(frame.locator("#col-poll-interval"), duration_s=0.65, dx_frac=0.3)
    wait_until(t0, 19.5)
    choreo.move_to_locator(frame.locator("#col-storage"), duration_s=0.55, dx_frac=0.3)

    # 23.0-35.0s: Day 3 of 3, 72 / 72 h logged, Missed polls: 0
    wait_until(t0, 23.5)
    choreo.move_to_locator(frame.locator("#col-day-label"), duration_s=0.6)
    wait_until(t0, 27.5)
    choreo.move_to_locator(frame.locator("#col-hours-logged"), duration_s=0.6, dx_frac=0.4)
    wait_until(t0, 31.5)
    choreo.move_to_locator(frame.locator("#col-missed-polls"), duration_s=0.55, dx_frac=0.3)

    # 35.0-44.0s: Sync button + hold through hand-off
    wait_until(t0, 35.2)
    choreo.move_to_locator(page.locator('[data-testid="stButton"] button').first, duration_s=0.65)
    wait_until(t0, 44.2)


def run_member2_sequence(page: Page, frame: FrameLocator, choreo: DemoChoreographer) -> None:
    """
    Synced to Member 2 (Amshah)'s 45.2s speech (trimmed 00:01.2-00:46.4):
      0.0-14.0s: Sweep Forecast vs observed chart (Observed, Forecast, shaded band, Now, Error=obs-fcst)
     14.0-17.0s: Click "All" ("Switching to All data...")
     17.0-24.0s: Scroll down to Forecast accuracy & Error by horizon; trace Temperature row (MAE, Bias)
     24.0-33.0s: Trace Error by horizon bars (+1 h -> +6 h -> +24 h)
     33.0-46.0s: Trace Rain callout banner ("Rain hit rate jumps from 69%... Over to Hafiz.")
    """
    t0 = time.perf_counter()

    # 0.0-14.0s: Sweep Temperature chart left-to-right past the Now divider
    wait_until(t0, 0.8)
    sweep_chart_tooltip(frame, choreo, start_frac=0.14, end_frac=0.77, duration_s=9.8, steps=30)
    wait_until(t0, 13.8)

    # 14.0-17.0s: Click "All" right as Amshah says "Switching to All data"
    all_btn = page.locator('[data-testid="stButtonGroup"] button', has_text="All").first
    choreo.click_locator(all_btn, duration_s=0.55)
    time.sleep(0.5)
    frame = wait_for_dashboard_ready(page)
    choreo.ensure_cursor()

    # 17.0-24.0s: Scroll down smoothly to Forecast accuracy & Error by horizon, trace Temperature row
    choreo.smooth_scroll(delta_y=520, duration_s=0.95, steps=18)
    temp_row = frame.locator("#accuracy-tbody tr").first
    choreo.move_to_locator(temp_row, duration_s=0.55, dx_frac=0.25)
    wait_until(t0, 20.5)
    choreo.move_to_locator(temp_row, duration_s=0.65, dx_frac=0.82)

    # 24.0-33.0s: Trace Error by horizon bars (+1h -> +6h -> +24h)
    wait_until(t0, 24.0)
    horizon_rows = frame.locator("#horizon-list .horizon-row")
    if horizon_rows.count() >= 4:
        choreo.move_to_locator(horizon_rows.nth(0), duration_s=0.6, dx_frac=0.72)
        wait_until(t0, 27.2)
        choreo.move_to_locator(horizon_rows.nth(1), duration_s=0.45, dx_frac=0.72)
        wait_until(t0, 29.8)
        choreo.move_to_locator(horizon_rows.nth(3), duration_s=0.5, dx_frac=0.82)

    # 33.0-46.0s: Trace Rain callout banner and hold cleanly until hand-off
    wait_until(t0, 33.2)
    choreo.move_to_locator(frame.locator("#rain-callout"), duration_s=0.7, dx_frac=0.42)
    wait_until(t0, 46.2)


def transcode_webm_to_mp4(webm_path: Path, mp4_path: Path, trim_start_s: float = 0.0) -> None:
    """Transcode Playwright's VP8 .webm into 1280x800 30fps H.264 .mp4, trimming initial load."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe,
        "-y",
        "-ss",
        f"{max(0.0, trim_start_s):.2f}",
        "-i",
        str(webm_path),
        "-vf",
        "fps=30,scale=1280:800",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(mp4_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def record_clip(clip_name: str, runner) -> Path:
    """Record a single choreographed session and export it as an MP4 in docs/recordings/."""
    out_mp4 = RECORDINGS_DIR / clip_name
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_video_dir = Path(tmp_dir)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=CHROME_PATH,
                headless=True,
                args=["--disable-gpu-vsync"],
            )
            context = browser.new_context(
                viewport=VIEWPORT,
                record_video_dir=str(tmp_video_dir),
                record_video_size=VIEWPORT,
            )
            page_start = time.perf_counter()
            page = context.new_page()
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            frame = wait_for_dashboard_ready(page)
            choreo = DemoChoreographer(page)
            load_elapsed = time.perf_counter() - page_start

            runner(page, frame, choreo)

            video = page.video
            context.close()
            browser.close()
            raw_webm = Path(video.path())

        transcode_webm_to_mp4(raw_webm, out_mp4, trim_start_s=load_elapsed)
    return out_mp4


def main() -> None:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/2] Recording speech-synced Member 1 dashboard...")
    m1 = record_clip("member1_dashboard.mp4", run_member1_sequence)
    print(f"  -> Saved {m1} ({m1.stat().st_size // 1024} KB)")

    print("[2/2] Recording speech-synced Member 2 dashboard...")
    m2 = record_clip("member2_dashboard.mp4", run_member2_sequence)
    print(f"  -> Saved {m2} ({m2.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
