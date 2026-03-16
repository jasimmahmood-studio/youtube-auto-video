#!/usr/bin/env python3
"""
Create a video from a script: fetch stock footage, generate narration via HeyGen,
assemble with FFmpeg, and burn eye-comfort subtitles.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

HEYGEN_API_BASE = "https://api.heygen.com"
PEXELS_API_BASE = "https://api.pexels.com"

# Subtitle configuration — eye-comfort defaults
SUBTITLE_CONFIG = {
    "font_family": "Montserrat-Bold",
    "font_size": 26,
    "primary_color": "white",
    "highlight_color": "#FFD700",
    "bg_color": "black@0.6",
    "margin_bottom": 50,
    "max_chars_per_line": 42,
    "max_lines": 2,
    "outline_width": 2,
}

FONT_PATH = Path(__file__).parent.parent / "assets" / "fonts" / "Montserrat-Bold.ttf"


# ─── Stock Footage (Pexels) ──────────────────────────────────────────

def fetch_stock_clips(queries, count_per_query=2, min_duration=5):
    """Fetch stock video clips from Pexels for each query."""
    if not PEXELS_API_KEY:
        print("ERROR: PEXELS_API_KEY not set in .env")
        sys.exit(1)

    headers = {"Authorization": PEXELS_API_KEY}
    clips = []

    for query in queries:
        url = f"{PEXELS_API_BASE}/videos/search"
        params = {
            "query": query,
            "per_page": count_per_query * 2,  # Fetch extra for filtering
            "size": "medium",
            "orientation": "landscape",
        }

        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"WARNING: Pexels search failed for '{query}': {resp.status_code}")
            continue

        videos = resp.json().get("videos", [])
        added = 0

        for video in videos:
            if added >= count_per_query:
                break
            duration = video.get("duration", 0)
            if duration < min_duration:
                continue

            # Get the HD file
            video_files = video.get("video_files", [])
            hd_files = [f for f in video_files if f.get("height", 0) >= 720]
            if not hd_files:
                hd_files = video_files

            if hd_files:
                best_file = sorted(hd_files, key=lambda x: x.get("height", 0), reverse=True)[0]
                clips.append({
                    "url": best_file["link"],
                    "query": query,
                    "duration": duration,
                    "width": best_file.get("width", 1920),
                    "height": best_file.get("height", 1080),
                })
                added += 1

    if not clips:
        print("WARNING: No stock clips found. Trying generic fallback queries...")
        fallback_queries = ["technology abstract", "city timelapse", "nature landscape", "office work"]
        return fetch_stock_clips(fallback_queries, count_per_query=2, min_duration=5)

    print(f"Found {len(clips)} stock clips for {len(queries)} queries")
    return clips


def download_clip(url, output_path):
    """Download a video clip to a local file."""
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path


# ─── Narration (HeyGen) ─────────────────────────────────────────────

def generate_narration(script_text, voice_id="Matthew"):
    """Generate narration audio using HeyGen's text-to-speech API."""
    if not HEYGEN_API_KEY:
        print("ERROR: HEYGEN_API_KEY not set in .env")
        sys.exit(1)

    headers = {
        "X-Api-Key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
    }

    # Create TTS audio via HeyGen
    payload = {
        "text": script_text,
        "voice_id": voice_id,
        "speed": 1.0,
        "pitch": 0,
    }

    # HeyGen v2 audio generation endpoint
    resp = requests.post(
        f"{HEYGEN_API_BASE}/v2/voice/generate",
        headers=headers,
        json=payload,
    )

    if resp.status_code != 200:
        print(f"ERROR: HeyGen TTS failed: {resp.status_code} - {resp.text}")
        sys.exit(1)

    result = resp.json()
    audio_url = result.get("data", {}).get("url")
    word_timestamps = result.get("data", {}).get("word_timestamps", [])

    if not audio_url:
        print("ERROR: No audio URL returned from HeyGen")
        sys.exit(1)

    return {
        "audio_url": audio_url,
        "duration": result.get("data", {}).get("duration", 0),
        "word_timestamps": word_timestamps,
    }


def download_audio(audio_url, output_path):
    """Download narration audio."""
    resp = requests.get(audio_url, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path


# ─── Subtitle Generation ────────────────────────────────────────────

def generate_subtitle_filter(word_timestamps, config=None):
    """
    Generate FFmpeg drawtext filter chain for word-by-word subtitles.

    The 'eye-comfort' approach: show 4-6 words at a time, highlighting the
    current word in gold while others stay white. This reduces cognitive load
    compared to showing one word at a time (too fast) or full sentences (too much to read).
    """
    cfg = config or SUBTITLE_CONFIG
    filters = []

    if not word_timestamps:
        return ""

    # Group words into subtitle chunks (4-6 words each)
    chunks = []
    current_chunk = []
    current_chars = 0

    for wt in word_timestamps:
        word = wt.get("word", "")
        start = wt.get("start", 0)
        end = wt.get("end", 0)

        current_chunk.append({"word": word, "start": start, "end": end})
        current_chars += len(word) + 1

        # Break chunk at sentence boundaries or character limit
        if (current_chars >= cfg["max_chars_per_line"]
                or word.endswith((".", "!", "?", ","))
                or len(current_chunk) >= 6):
            chunks.append(current_chunk)
            current_chunk = []
            current_chars = 0

    if current_chunk:
        chunks.append(current_chunk)

    # Build FFmpeg drawtext filters for each chunk
    font_path = str(FONT_PATH) if FONT_PATH.exists() else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    for chunk in chunks:
        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]
        full_text = " ".join(w["word"] for w in chunk)

        # Base text (white, all words)
        filters.append(
            f"drawtext=text='{_escape_ffmpeg(full_text)}':"
            f"fontfile='{font_path}':"
            f"fontsize={cfg['font_size']}:"
            f"fontcolor={cfg['primary_color']}:"
            f"borderw={cfg['outline_width']}:"
            f"bordercolor=black:"
            f"box=1:boxcolor={cfg['bg_color']}:boxborderw=8:"
            f"x=(w-text_w)/2:y=h-{cfg['margin_bottom']}-text_h:"
            f"enable='between(t,{chunk_start},{chunk_end})'"
        )

        # Highlight current word overlay (gold)
        # This creates a separate drawtext for each word's active period
        x_offset = 0
        for i, wt in enumerate(chunk):
            word = wt["word"]
            w_start = wt["start"]
            w_end = wt["end"]

            # Calculate x position for this word within the chunk
            # We approximate character width as fontsize * 0.6
            char_width = cfg["font_size"] * 0.55
            prefix_len = len(" ".join(w["word"] for w in chunk[:i]))
            if i > 0:
                prefix_len += 1  # space before word

            # Highlight just this word in gold
            filters.append(
                f"drawtext=text='{_escape_ffmpeg(word)}':"
                f"fontfile='{font_path}':"
                f"fontsize={cfg['font_size']}:"
                f"fontcolor={cfg['highlight_color']}:"
                f"borderw={cfg['outline_width']}:"
                f"bordercolor=black:"
                f"x=(w-text_w)/2-{int(len(full_text)*char_width/2)}+{int(prefix_len*char_width)}:"
                f"y=h-{cfg['margin_bottom']}-text_h:"
                f"enable='between(t,{w_start},{w_end})'"
            )

    return ",".join(filters)


def _escape_ffmpeg(text):
    """Escape special characters for FFmpeg drawtext."""
    return (text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace("%", "%%")
            .replace("[", "\\[")
            .replace("]", "\\]"))


# ─── Video Assembly (FFmpeg) ─────────────────────────────────────────

def assemble_video(clips_dir, audio_path, subtitle_filter, output_path, bg_music_path=None):
    """
    Assemble final video: stock clips + narration audio + subtitles.
    """
    # Check FFmpeg availability
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: FFmpeg not found. Install it: sudo apt-get install ffmpeg -y")
        sys.exit(1)

    # Get audio duration
    probe = subprocess.run(
        ["ffprobe", "-i", audio_path, "-show_entries", "format=duration",
         "-v", "quiet", "-of", "csv=p=0"],
        capture_output=True, text=True
    )
    audio_duration = float(probe.stdout.strip())

    # List all clip files
    clip_files = sorted(Path(clips_dir).glob("*.mp4"))
    if not clip_files:
        print("ERROR: No clip files found in", clips_dir)
        sys.exit(1)

    # Create a concat file for clips
    concat_file = Path(clips_dir) / "concat.txt"
    total_clip_duration = 0

    with open(concat_file, "w") as f:
        while total_clip_duration < audio_duration:
            for clip in clip_files:
                if total_clip_duration >= audio_duration:
                    break
                f.write(f"file '{clip.resolve()}'\n")
                # Estimate clip duration (~10s each)
                total_clip_duration += 10

    # Step 1: Concatenate clips to match audio duration
    concat_video = Path(clips_dir) / "concat.mp4"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-t", str(audio_duration),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an",
        str(concat_video)
    ]
    subprocess.run(cmd_concat, capture_output=True, check=True)

    # Step 2: Merge video + audio + subtitles
    cmd_final = [
        "ffmpeg", "-y",
        "-i", str(concat_video),
        "-i", audio_path,
    ]

    # Add background music if provided
    if bg_music_path and Path(bg_music_path).exists():
        cmd_final.extend(["-i", bg_music_path])

    # Video filter: subtitles
    vf = subtitle_filter if subtitle_filter else "null"
    cmd_final.extend(["-vf", vf])

    # Audio mixing
    if bg_music_path and Path(bg_music_path).exists():
        # Mix narration (full volume) + music (10% volume)
        cmd_final.extend([
            "-filter_complex", "[1:a]volume=1.0[narr];[2:a]volume=0.1[music];[narr][music]amix=inputs=2:duration=first[aout]",
            "-map", "0:v", "-map", "[aout]",
        ])
    else:
        cmd_final.extend(["-map", "0:v", "-map", "1:a"])

    cmd_final.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", str(audio_duration),
        str(output_path)
    ])

    result = subprocess.run(cmd_final, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: FFmpeg final assembly failed:\n{result.stderr}")
        sys.exit(1)

    # Cleanup temp concat video
    concat_video.unlink(missing_ok=True)
    concat_file.unlink(missing_ok=True)

    print(f"Video assembled: {output_path} ({audio_duration:.1f}s)")
    return str(output_path)


# ─── Main Pipeline ───────────────────────────────────────────────────

def create_video(script_path, voice_id="Matthew", bg_music=None, output=None):
    """Full video creation pipeline."""
    # Load script
    with open(script_path) as f:
        script_data = json.load(f)

    script_text = script_data["script_text"]
    footage_queries = script_data.get("stock_footage_queries", [])

    print(f"Creating video for: {script_data['title']}")
    print(f"Script: {len(script_text.split())} words")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        clips_dir = tmpdir / "clips"
        clips_dir.mkdir()

        # Step 1: Fetch stock footage
        print("\n[1/4] Fetching stock footage from Pexels...")
        clips = fetch_stock_clips(footage_queries, count_per_query=2)
        for i, clip in enumerate(clips):
            clip_path = clips_dir / f"clip_{i:03d}.mp4"
            print(f"  Downloading: {clip['query']} ({clip['duration']}s)")
            download_clip(clip["url"], str(clip_path))

        # Step 2: Generate narration
        print("\n[2/4] Generating narration via HeyGen...")
        narration = generate_narration(script_text, voice_id=voice_id)
        audio_path = tmpdir / "narration.mp3"
        download_audio(narration["audio_url"], str(audio_path))
        print(f"  Narration: {narration['duration']:.1f}s")

        # Step 3: Generate subtitle filter
        print("\n[3/4] Building eye-comfort subtitles...")
        word_timestamps = narration.get("word_timestamps", [])
        subtitle_filter = generate_subtitle_filter(word_timestamps)
        if subtitle_filter:
            print(f"  Subtitles: {len(word_timestamps)} words with word-by-word highlight")
        else:
            print("  WARNING: No word timestamps from HeyGen, subtitles will be skipped")

        # Step 4: Assemble video
        print("\n[4/4] Assembling final video...")
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_path = output or f"output/video_{datetime.now().strftime('%Y-%m-%d')}.mp4"

        assemble_video(
            clips_dir=str(clips_dir),
            audio_path=str(audio_path),
            subtitle_filter=subtitle_filter,
            output_path=output_path,
            bg_music_path=bg_music,
        )

    print(f"\nVideo created successfully: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Create a video from a script")
    parser.add_argument("--script", required=True, help="Path to script JSON file")
    parser.add_argument("--voice", default="Matthew", help="HeyGen voice ID (default: Matthew)")
    parser.add_argument("--music", default=None, help="Path to background music file")
    parser.add_argument("--output", default=None, help="Output video file path")
    args = parser.parse_args()

    create_video(args.script, voice_id=args.voice, bg_music=args.music, output=args.output)


if __name__ == "__main__":
    main()
