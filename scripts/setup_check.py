#!/usr/bin/env python3
"""
Verify all API credentials and dependencies are properly configured.
Run this before the first pipeline execution.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def check_env_var(name, required=True):
    """Check if an environment variable is set."""
    value = os.getenv(name)
    if value:
        # Mask the value for security
        masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "****"
        print(f"  ✓ {name} = {masked}")
        return True
    else:
        status = "✗ MISSING" if required else "○ Optional"
        print(f"  {status} {name}")
        return not required


def check_youtube_api():
    """Test YouTube Data API connectivity."""
    import requests
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return False

    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet", "chart": "mostPopular", "maxResults": 1, "key": api_key}
    )
    if resp.status_code == 200:
        print("  ✓ YouTube API: Connected")
        return True
    else:
        print(f"  ✗ YouTube API: {resp.status_code} - {resp.json().get('error', {}).get('message', '')}")
        return False


def check_pexels_api():
    """Test Pexels API connectivity."""
    import requests
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return False

    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": api_key},
        params={"query": "test", "per_page": 1}
    )
    if resp.status_code == 200:
        print("  ✓ Pexels API: Connected")
        return True
    else:
        print(f"  ✗ Pexels API: {resp.status_code}")
        return False


def check_heygen_api():
    """Test HeyGen API connectivity."""
    import requests
    api_key = os.getenv("HEYGEN_API_KEY")
    if not api_key:
        return False

    resp = requests.get(
        "https://api.heygen.com/v1/voice.list",
        headers={"X-Api-Key": api_key}
    )
    if resp.status_code == 200:
        print("  ✓ HeyGen API: Connected")
        voices = resp.json().get("data", {}).get("voices", [])
        print(f"    Available voices: {len(voices)}")
        return True
    else:
        print(f"  ✗ HeyGen API: {resp.status_code}")
        return False


def check_ffmpeg():
    """Check FFmpeg installation."""
    import subprocess
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        version = result.stdout.split("\n")[0] if result.stdout else "unknown"
        print(f"  ✓ FFmpeg: {version}")
        return True
    except FileNotFoundError:
        print("  ✗ FFmpeg: Not installed")
        return False


def main():
    print("=" * 60)
    print("YouTube Auto Video — Setup Check")
    print("=" * 60)

    all_ok = True

    # Check environment variables
    print("\n[1] Environment Variables:")
    checks = [
        ("YOUTUBE_API_KEY", True),
        ("YOUTUBE_CLIENT_ID", True),
        ("YOUTUBE_CLIENT_SECRET", True),
        ("YOUTUBE_REFRESH_TOKEN", True),
        ("HEYGEN_API_KEY", True),
        ("PEXELS_API_KEY", True),
        ("OPENAI_API_KEY", False),
        ("ANTHROPIC_API_KEY", False),
    ]
    for name, required in checks:
        if not check_env_var(name, required):
            all_ok = False

    # Check AI backend
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    if not has_openai and not has_anthropic:
        print("  ✗ No AI backend configured (need OPENAI_API_KEY or ANTHROPIC_API_KEY)")
        all_ok = False

    # Check API connectivity
    print("\n[2] API Connectivity:")
    try:
        import requests
        if not check_youtube_api():
            all_ok = False
        if not check_pexels_api():
            all_ok = False
        if not check_heygen_api():
            all_ok = False
    except ImportError:
        print("  ✗ 'requests' package not installed")
        all_ok = False

    # Check FFmpeg
    print("\n[3] System Dependencies:")
    if not check_ffmpeg():
        all_ok = False

    # Check font
    font_path = Path(__file__).parent.parent / "assets" / "fonts" / "Montserrat-Bold.ttf"
    if font_path.exists():
        print(f"  ✓ Subtitle font: {font_path}")
    else:
        print("  ○ Subtitle font: Not downloaded (run setup_fonts.py)")

    # Summary
    print(f"\n{'='*60}")
    if all_ok:
        print("All checks passed! You're ready to run the pipeline.")
        print("  python scripts/run_daily.py --dry-run")
    else:
        print("Some checks failed. Fix the issues above before running.")
    print("=" * 60)


if __name__ == "__main__":
    main()
