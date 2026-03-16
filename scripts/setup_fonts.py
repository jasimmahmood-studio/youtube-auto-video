#!/usr/bin/env python3
"""
Download the Montserrat Bold font for subtitle rendering.
"""

import os
import sys
from pathlib import Path

import requests

FONT_URL = "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf"
FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"
FONT_PATH = FONT_DIR / "Montserrat-Bold.ttf"


def download_font():
    """Download Montserrat Bold font."""
    if FONT_PATH.exists():
        print(f"Font already exists: {FONT_PATH}")
        return

    FONT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading Montserrat Bold...")
    resp = requests.get(FONT_URL, allow_redirects=True)

    if resp.status_code != 200:
        print(f"ERROR: Failed to download font: {resp.status_code}")
        print("Fallback: Using system font (DejaVu Sans Bold)")
        return

    with open(FONT_PATH, "wb") as f:
        f.write(resp.content)

    print(f"Font saved to: {FONT_PATH}")


def check_ffmpeg():
    """Check if FFmpeg is installed."""
    import subprocess
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        version = result.stdout.split("\n")[0]
        print(f"FFmpeg: {version}")
        return True
    except FileNotFoundError:
        print("WARNING: FFmpeg not found!")
        print("Install it:")
        print("  Linux: sudo apt-get install ffmpeg -y")
        print("  macOS: brew install ffmpeg")
        print("  Windows: choco install ffmpeg")
        return False


if __name__ == "__main__":
    print("Setting up YouTube Auto Video dependencies...\n")
    download_font()
    print()
    check_ffmpeg()
    print("\nSetup complete!")
