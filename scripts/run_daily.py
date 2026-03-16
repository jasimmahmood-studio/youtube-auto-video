#!/usr/bin/env python3
"""
Daily orchestrator: runs the full pipeline (trending → script → video → upload).
Handles category rotation, error recovery, logging, and scheduling.
"""

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SCRIPTS_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPTS_DIR.parent / "config"
CATEGORIES_FILE = CONFIG_DIR / "categories.json"


def _load_config():
    """Load category config and build day rotation."""
    if CATEGORIES_FILE.exists():
        with open(CATEGORIES_FILE) as f:
            data = json.load(f)
        categories = data.get("categories", {})
        day_rotation_raw = data.get("day_rotation", {})
        # Convert string keys to int
        day_rotation = {int(k): v for k, v in day_rotation_raw.items()}
    else:
        categories = {}
        day_rotation = {}

    # Filter by ENABLED_CATEGORIES from .env
    env_enabled = os.getenv("ENABLED_CATEGORIES", "").strip()
    if env_enabled:
        enabled = [c.strip().lower() for c in env_enabled.split(",") if c.strip()]
    else:
        enabled = list(categories.keys())

    # If no day_rotation in config, auto-build from enabled categories
    if not day_rotation:
        day_rotation = {}
        for i in range(7):
            if i < len(enabled):
                day_rotation[i] = enabled[i]
            else:
                day_rotation[i] = "all"

    return categories, enabled, day_rotation


_CATEGORIES, ENABLED_CATEGORIES, DAY_CATEGORY_MAP = _load_config()
_DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
_rotation_str = ', '.join(f"{_DAY_NAMES[k]}={v}" for k, v in sorted(DAY_CATEGORY_MAP.items()) if k < 7)
print(f"Category rotation: {_rotation_str}")


def get_todays_category(override=None):
    """Get the category for today based on day-of-week rotation."""
    if override:
        return override
    day_of_week = datetime.now().weekday()
    return DAY_CATEGORY_MAP.get(day_of_week, "all")


def run_step(name, cmd, dry_run=False):
    """Run a pipeline step and return success/failure."""
    print(f"\n{'='*60}")
    print(f"STEP: {name}")
    print(f"{'='*60}")

    if dry_run:
        print(f"  [DRY RUN] Would run: {' '.join(cmd)}")
        return True, "dry_run"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per step
        )

        if result.stdout:
            print(result.stdout)
        if result.returncode != 0:
            print(f"ERROR in {name}:")
            print(result.stderr)
            return False, result.stderr

        return True, result.stdout

    except subprocess.TimeoutExpired:
        print(f"ERROR: {name} timed out after 10 minutes")
        return False, "timeout"
    except Exception as e:
        print(f"ERROR: {name} failed with exception: {e}")
        return False, str(e)


def _clean_output():
    """Remove previous output files (videos, scripts, topics) before a fresh run."""
    output_dir = Path("output")
    if not output_dir.exists():
        return
    removed = 0
    for f in output_dir.iterdir():
        if f.is_file() and f.suffix in (".mp4", ".json", ".srt", ".txt"):
            f.unlink()
            removed += 1
    if removed:
        print(f"Cleaned {removed} old output file(s)")


def run_pipeline(category=None, region="US", voice="Brian", music=None,
                 privacy="public", dry_run=False, skip_upload=False):
    """Run the full video production pipeline."""
    today = datetime.now().strftime("%Y-%m-%d")
    category = get_todays_category(category)

    print(f"YouTube Auto Video — Daily Pipeline")
    print(f"Date: {today}")
    print(f"Category: {category}")
    print(f"Region: {region}")
    print(f"Dry run: {dry_run}")
    print(f"{'='*60}")

    log = {
        "date": today,
        "category": category,
        "region": region,
        "steps": {},
        "success": False,
        "started_at": datetime.now().isoformat(),
    }

    # Ensure output and logs directories exist
    Path("output").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    # Clean previous output files
    if not dry_run:
        _clean_output()

    # Step 1: Fetch trending topic
    topic_file = f"output/trending_topic_{today}.json"
    success, output = run_step(
        "Fetch Trending Topic",
        [sys.executable, str(SCRIPTS_DIR / "fetch_trending.py"),
         "--category", category, "--region", region, "--output", topic_file],
        dry_run=dry_run
    )
    log["steps"]["fetch_trending"] = {"success": success, "output": topic_file}
    if not success and not dry_run:
        _save_log(log, today)
        return log

    # Step 2: Generate script
    script_file = f"output/script_{today}.json"
    success, output = run_step(
        "Generate Script",
        [sys.executable, str(SCRIPTS_DIR / "generate_script.py"),
         "--topic", topic_file, "--ai", "claude", "--output", script_file],
        dry_run=dry_run
    )
    log["steps"]["generate_script"] = {"success": success, "output": script_file}
    if not success and not dry_run:
        _save_log(log, today)
        return log

    # Step 3: Create video
    video_file = f"output/video_{today}.mp4"
    cmd = [sys.executable, str(SCRIPTS_DIR / "create_video.py"),
           "--script", script_file, "--voice", voice, "--output", video_file]
    if music:
        cmd.extend(["--music", music])

    success, output = run_step("Create Video", cmd, dry_run=dry_run)
    log["steps"]["create_video"] = {"success": success, "output": video_file}
    if not success and not dry_run:
        _save_log(log, today)
        return log

    # Step 4: Upload to YouTube
    if skip_upload:
        print("\n[SKIPPED] YouTube upload (--skip-upload flag)")
        log["steps"]["upload"] = {"success": True, "output": "skipped"}
    else:
        success, output = run_step(
            "Upload to YouTube",
            [sys.executable, str(SCRIPTS_DIR / "upload_youtube.py"),
             "--video", video_file, "--metadata", script_file, "--privacy", privacy],
            dry_run=dry_run
        )
        log["steps"]["upload"] = {"success": success, "output": output}
        if not success and not dry_run:
            _save_log(log, today)
            return log

    # Success!
    log["success"] = True
    log["completed_at"] = datetime.now().isoformat()

    # Print summary
    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE")
    print(f"{'='*60}")
    if not dry_run and Path(script_file).exists():
        with open(script_file) as f:
            script_data = json.load(f)
        print(f"Topic: {script_data.get('title', 'N/A')}")
        print(f"Category: {category}")
        print(f"Video: {video_file}")

    # Cleanup temp files (keep outputs)
    _cleanup(today)

    _save_log(log, today)
    return log


def _save_log(log, today):
    """Save daily run log."""
    log_file = f"logs/run_{today}.json"
    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)
    print(f"\nLog saved: {log_file}")


def _cleanup(today):
    """Clean up temporary files, keep final outputs."""
    # Keep: video, script, topic JSON, logs
    # Remove: temp clips, narration audio, concat files
    pass  # Stock clips are in tempdir and auto-cleaned


def setup_cron():
    """Set up a daily cron job to run the pipeline."""
    script_path = Path(__file__).resolve()
    python_path = sys.executable

    cron_line = f"0 10 * * * cd {script_path.parent.parent} && {python_path} {script_path} >> logs/cron.log 2>&1"

    print(f"Adding cron job: {cron_line}")

    # Read existing crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    # Check if already scheduled
    if str(script_path) in existing:
        print("Cron job already exists. Updating...")
        lines = [l for l in existing.split("\n") if str(script_path) not in l]
        existing = "\n".join(lines)

    # Add new cron
    new_crontab = existing.rstrip() + "\n" + cron_line + "\n"
    subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)

    print("Cron job scheduled: Daily at 10:00 AM")


def main():
    parser = argparse.ArgumentParser(description="YouTube Auto Video — Daily Pipeline")
    valid_cats = ["all"] + list(_CATEGORIES.keys())
    parser.add_argument("--category", default=None,
                        choices=valid_cats,
                        help=f"Override category (default: auto-rotates by day). Available: {', '.join(valid_cats)}")
    parser.add_argument("--region", default="US", help="YouTube region code (default: US)")
    parser.add_argument("--voice", default="Brian", help="HeyGen voice (default: Brian)")
    parser.add_argument("--music", default=None, help="Background music file path")
    parser.add_argument("--privacy", default="public",
                        choices=["public", "private", "unlisted"],
                        help="YouTube privacy (default: public)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview pipeline without executing")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Run everything except YouTube upload")
    parser.add_argument("--schedule", action="store_true",
                        help="Set up daily cron job at 10 AM")
    args = parser.parse_args()

    if args.schedule:
        setup_cron()
        return

    run_pipeline(
        category=args.category,
        region=args.region,
        voice=args.voice,
        music=args.music,
        privacy=args.privacy,
        dry_run=args.dry_run,
        skip_upload=args.skip_upload,
    )


if __name__ == "__main__":
    main()
