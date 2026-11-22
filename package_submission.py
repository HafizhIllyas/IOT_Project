"""
Package clean source code into a submission-ready ZIP archive
(excluding all executables, __pycache__, virtual environments, and build artifacts)
per UTP TFB2093 submission instructions: "Source code (zip and remove all executables)".
"""

from __future__ import annotations

import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ZIP_PATH = BASE_DIR / "TFB2093_Seri_Iskandar_Weather_IoT_SourceCode.zip"

EXCLUDED_DIRS = {"__pycache__", ".git", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache"}
EXCLUDED_EXTS = {".exe", ".dll", ".so", ".dylib", ".pyc", ".pyo", ".zip", ".docx", ".mp4", ".webm"}


def create_clean_zip() -> Path:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    included_files = []
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(BASE_DIR.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(BASE_DIR)
            if any(part in EXCLUDED_DIRS for part in rel.parts):
                continue
            if path.suffix.lower() in EXCLUDED_EXTS:
                continue
            zf.write(path, arcname=str(rel))
            included_files.append(str(rel))

    print(f"[OK] Created clean submission archive: {ZIP_PATH.name} ({len(included_files)} files)")
    for f in included_files:
        print(f"  - {f}")
    return ZIP_PATH


if __name__ == "__main__":
    create_clean_zip()
