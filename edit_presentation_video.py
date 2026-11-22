"""
Composite Member 1 and Member 2's webcam recordings + normalized voiceovers onto
their speech-synced 1280x800 dashboard recordings, and concatenate both parts.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import imageio_ffmpeg

BASE_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = BASE_DIR / "docs" / "recordings"

MEMBER1_WEBCAM = Path(
    r"C:\Users\hafiz\.gemini\antigravity\brain\459bd421-d400-42c8-9082-3cfe19cd0544\.user_uploaded\media_1795338627059_2fcbd3fe.mp4"
)
MEMBER2_WEBCAM = Path(
    r"C:\Users\hafiz\.gemini\antigravity\brain\459bd421-d400-42c8-9082-3cfe19cd0544\.user_uploaded\media_1795338627050_298e70aa.mp4"
)


def composite_member_video(
    dash_mp4: Path,
    webcam_mp4: Path,
    out_mp4: Path,
    cam_start_s: float,
    duration_s: float,
    crop_expr: str,
) -> Path:
    """Overlay cropped 4:3 webcam PiP in bottom-right corner with loudnorm audio."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        f"[0:v]scale=1280:800,fps=30,setpts=PTS-STARTPTS[bg];"
        f"[1:v]{crop_expr},scale=234:176,fps=30,pad=240:182:3:3:#58A6FF,setpts=PTS-STARTPTS[pip];"
        f"[bg][pip]overlay=x=W-w-20:y=H-h-20:shortest=1[vout];"
        f"[1:a]asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[aout]"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(dash_mp4),
        "-ss",
        f"{cam_start_s:.2f}",
        "-t",
        f"{duration_s:.2f}",
        "-i",
        str(webcam_mp4),
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-t",
        f"{duration_s:.2f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_mp4


def concat_edited_videos(part1_mp4: Path, part2_mp4: Path, out_mp4: Path) -> Path:
    """Concatenate Member 1 and Member 2 edited clips seamlessly."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write(f"file '{part1_mp4.as_posix()}'\n")
        tf.write(f"file '{part2_mp4.as_posix()}'\n")
        list_path = Path(tf.name)

    try:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(out_mp4),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        list_path.unlink(missing_ok=True)
    return out_mp4


def main() -> None:
    m1_dash = RECORDINGS_DIR / "member1_dashboard.mp4"
    m2_dash = RECORDINGS_DIR / "member2_dashboard.mp4"

    m1_out = RECORDINGS_DIR / "member1_edited.mp4"
    m2_out = RECORDINGS_DIR / "member2_edited.mp4"
    combined_out = RECORDINGS_DIR / "member1_and_2_edited_combined.mp4"

    print("[1/3] Compositing Member 1 (dashboard + PiP webcam + normalized audio)...")
    composite_member_video(
        dash_mp4=m1_dash,
        webcam_mp4=MEMBER1_WEBCAM,
        out_mp4=m1_out,
        cam_start_s=0.0,
        duration_s=43.5,
        crop_expr="crop=576:432:0:290",
    )
    print(f"  -> Saved {m1_out} ({m1_out.stat().st_size // 1024} KB)")

    print("[2/3] Compositing Member 2 (dashboard + PiP webcam + normalized audio)...")
    composite_member_video(
        dash_mp4=m2_dash,
        webcam_mp4=MEMBER2_WEBCAM,
        out_mp4=m2_out,
        cam_start_s=1.2,
        duration_s=45.2,
        crop_expr="crop=960:720:160:0",
    )
    print(f"  -> Saved {m2_out} ({m2_out.stat().st_size // 1024} KB)")

    print("[3/3] Concatenating Member 1 + Member 2...")
    concat_edited_videos(m1_out, m2_out, combined_out)
    print(f"  -> Saved {combined_out} ({combined_out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
