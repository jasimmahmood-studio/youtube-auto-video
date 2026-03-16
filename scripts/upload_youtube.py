#!/usr/bin/env python3
"""
Upload a video to YouTube with optimized metadata.
Uses YouTube Data API v3 with OAuth 2.0 authentication.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

# YouTube category mapping for our niches
CATEGORY_MAP = {
    "geopolitics": "25",    # News & Politics
    "health": "27",         # Education
    "wealth": "27",         # Education
    "relationship": "22",   # People & Blogs
}


def get_access_token():
    """Refresh the OAuth access token using the stored refresh token."""
    if not all([YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN]):
        print("ERROR: YouTube OAuth credentials not configured in .env")
        print("Run 'python scripts/youtube_auth.py' to set up OAuth first.")
        sys.exit(1)

    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "refresh_token": YOUTUBE_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    })

    if resp.status_code != 200:
        print(f"ERROR: Token refresh failed: {resp.status_code} - {resp.text}")
        sys.exit(1)

    return resp.json()["access_token"]


def upload_video(video_path, metadata, privacy="public", schedule_time=None):
    """
    Upload a video to YouTube using resumable upload protocol.

    Args:
        video_path: Path to the .mp4 file
        metadata: Dict with title, description, tags, category
        privacy: 'public', 'private', or 'unlisted'
        schedule_time: ISO datetime string for scheduled publishing (requires 'private' privacy)
    """
    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Build the video resource
    category = metadata.get("source_topic", {}).get("category", "health")
    category_id = CATEGORY_MAP.get(category, "27")

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": _build_description(metadata),
            "tags": metadata.get("tags", [])[:500],  # YouTube limit
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    # Add scheduled publish time if specified
    if schedule_time:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = schedule_time

    # Step 1: Initialize resumable upload
    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    init_resp = requests.post(init_url, headers=headers, json=body)

    if init_resp.status_code != 200:
        print(f"ERROR: Upload init failed: {init_resp.status_code} - {init_resp.text}")
        sys.exit(1)

    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        print("ERROR: No upload URL returned")
        sys.exit(1)

    # Step 2: Upload the video file
    file_size = os.path.getsize(video_path)
    print(f"Uploading {file_size / (1024*1024):.1f} MB...")

    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size),
            },
            data=f,
        )

    if upload_resp.status_code not in (200, 201):
        print(f"ERROR: Upload failed: {upload_resp.status_code} - {upload_resp.text}")
        sys.exit(1)

    result = upload_resp.json()
    video_id = result["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    print(f"\nVideo uploaded successfully!")
    print(f"URL: {video_url}")
    print(f"Status: {privacy}")

    # Log the upload
    _log_upload(video_id, video_url, metadata, privacy)

    return {"video_id": video_id, "url": video_url, "status": privacy}


def _build_description(metadata):
    """Build an SEO-optimized YouTube description."""
    desc = metadata.get("description", "")
    tags = metadata.get("tags", [])
    category = metadata.get("source_topic", {}).get("category", "")

    # Add hashtags
    hashtags = [f"#{tag.replace(' ', '')}" for tag in tags[:5]]
    hashtag_line = " ".join(hashtags)

    # Build full description
    full_desc = f"""{desc}

---

{hashtag_line}

Subscribe for daily videos on {category}, and more!
Hit the bell icon to never miss an update.

---

Disclaimer: This video is for informational and educational purposes only.
"""
    return full_desc.strip()


def _log_upload(video_id, video_url, metadata, privacy):
    """Log upload details to history."""
    history_dir = Path("history")
    history_dir.mkdir(exist_ok=True)
    log_file = history_dir / "uploads.json"

    uploads = []
    if log_file.exists():
        with open(log_file) as f:
            uploads = json.load(f)

    uploads.append({
        "video_id": video_id,
        "url": video_url,
        "title": metadata.get("title", ""),
        "category": metadata.get("source_topic", {}).get("category", ""),
        "privacy": privacy,
        "uploaded_at": datetime.now().isoformat(),
    })

    with open(log_file, "w") as f:
        json.dump(uploads, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Upload a video to YouTube")
    parser.add_argument("--video", required=True, help="Path to video file (.mp4)")
    parser.add_argument("--metadata", required=True, help="Path to script JSON with video metadata")
    parser.add_argument("--privacy", default="public", choices=["public", "private", "unlisted"],
                        help="Video privacy status (default: public)")
    parser.add_argument("--schedule", default=None,
                        help="Schedule publish time (ISO format, e.g., 2026-03-16T14:00:00Z)")
    args = parser.parse_args()

    # Validate inputs
    if not Path(args.video).exists():
        print(f"ERROR: Video file not found: {args.video}")
        sys.exit(1)
    if not Path(args.metadata).exists():
        print(f"ERROR: Metadata file not found: {args.metadata}")
        sys.exit(1)

    with open(args.metadata) as f:
        metadata = json.load(f)

    result = upload_video(args.video, metadata, privacy=args.privacy, schedule_time=args.schedule)
    print(f"\nDone! Video: {result['url']}")


if __name__ == "__main__":
    main()
