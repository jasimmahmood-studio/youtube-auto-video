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


# ─── Narration (HeyGen TTS) ──────────────────────────────────────────

# Map friendly voice names to actual HeyGen voice IDs
HEYGEN_VOICE_MAP = {
    "Brian": "f38a635bee7a4d1f9b0a654a31d050d2",        # Chill Brian (male)
    "Allison": "f8c69e517f424cafaecde32dde57096b",       # Allison (female)
    "Ivy": "cef3bc4e0a84424cafcde6f2cf466c97",           # Ivy (female)
    "John": "d92994ae0de34b2e8659b456a2f388b8",          # John Doe (male)
    "Mark": "5d8c378ba8c3434586081a52ac368738",           # Mark (male)
    "Monika": "97dd67ab8ce242b6a9e7689cb00c6414",        # Monika Sogam (female)
    "Hope": "42d00d4aac5441279d8536cd6b52c53c",          # Hope (female)
    # Fallback defaults
    "Matthew": "d92994ae0de34b2e8659b456a2f388b8",       # Maps to John Doe
    "Sara": "cef3bc4e0a84424cafcde6f2cf466c97",          # Maps to Ivy
    "Josh": "f38a635bee7a4d1f9b0a654a31d050d2",          # Maps to Chill Brian
}


def generate_narration(script_text, voice_id="Brian", output_path="narration.mp3"):
    """
    Generate narration audio using HeyGen's text-to-speech API.
    Endpoint: POST /v1/audio/text_to_speech
    Returns audio file with word-level timestamps for subtitle sync.
    """
    if not HEYGEN_API_KEY:
        print("ERROR: HEYGEN_API_KEY not set in .env")
        sys.exit(1)

    # Resolve friendly name to actual HeyGen voice ID
    resolved_id = HEYGEN_VOICE_MAP.get(voice_id, voice_id)
    print(f"  Voice: {voice_id} ({resolved_id[:12]}...)")

    headers = {
        "X-Api-Key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "text": script_text,
        "voice_id": resolved_id,
    }

    resp = requests.post(
        f"{HEYGEN_API_BASE}/v1/audio/text_to_speech",
        headers=headers,
        json=payload,
    )

    if resp.status_code != 200:
        print(f"ERROR: HeyGen TTS failed: {resp.status_code} - {resp.text[:300]}")
        sys.exit(1)

    result = resp.json()
    data = result.get("data", {})
    audio_url = data.get("url") or data.get("audio_url")
    word_timestamps_raw = data.get("word_timestamps", [])

    if not audio_url:
        # Some HeyGen responses nest differently
        audio_url = result.get("url") or result.get("audio_url")

    if not audio_url:
        print(f"ERROR: No audio URL in HeyGen response. Full response: {json.dumps(result)[:500]}")
        sys.exit(1)

    # Download the audio file
    audio_resp = requests.get(audio_url, stream=True)
    audio_resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in audio_resp.iter_content(chunk_size=8192):
            f.write(chunk)

    # Parse word timestamps into our format
    word_timestamps = []
    for wt in word_timestamps_raw:
        word_timestamps.append({
            "word": wt.get("word", wt.get("text", "")),
            "start": wt.get("start", wt.get("start_time", 0)),
            "end": wt.get("end", wt.get("end_time", 0)),
        })

    # If no word timestamps from API, estimate them from text
    if not word_timestamps:
        duration = _get_audio_duration(output_path)
        word_timestamps = _estimate_word_timestamps(script_text, duration)

    duration = data.get("duration") or _get_audio_duration(output_path)

    print(f"  Audio downloaded: {output_path}")
    return {
        "audio_path": output_path,
        "duration": duration,
        "word_timestamps": word_timestamps,
    }


def _estimate_word_timestamps(text, total_duration):
    """Estimate word timestamps when API doesn't provide them."""
    words = text.split()
    if not words or total_duration <= 0:
        return []

    time_per_word = total_duration / len(words)
    timestamps = []
    for i, word in enumerate(words):
        timestamps.append({
            "word": word,
            "start": round(i * time_per_word, 3),
            "end": round((i + 1) * time_per_word, 3),
        })
    return timestamps


def _parse_vtt_timestamps(vtt_path):
    """Parse word-level timestamps from SRT/VTT output."""
    timestamps = []
    if not Path(vtt_path).exists():
        return timestamps

    with open(vtt_path) as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for timestamp lines like: 00:00:00.000 --> 00:00:01.500
        if "-->" in line:
            parts = line.split("-->")
            start = _vtt_time_to_seconds(parts[0].strip())
            end = _vtt_time_to_seconds(parts[1].strip())
            # Next line is the text
            i += 1
            if i < len(lines):
                word = lines[i].strip()
                if word:
                    timestamps.append({"word": word, "start": start, "end": end})
        i += 1

    return timestamps


def _vtt_time_to_seconds(time_str):
    """Convert VTT timestamp (HH:MM:SS.mmm) to seconds."""
    parts = time_str.replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    return float(parts[0])


def _get_audio_duration(audio_path):
    """Get audio duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-i", audio_path, "-show_entries", "format=duration",
             "-v", "quiet", "-of", "csv=p=0"],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())
    except Exception:
        return 0


# ─── Subtitle Generation (SRT file approach) ──────────────────────────

def _seconds_to_srt_time(seconds):
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt_file(word_timestamps, output_path, config=None):
    """
    Generate an SRT subtitle file from word timestamps.

    Groups words into readable chunks (4-6 words, max 42 chars per line)
    for comfortable viewing — the 'eye-comfort' approach.
    """
    cfg = config or SUBTITLE_CONFIG

    if not word_timestamps:
        return None

    # Group words into subtitle chunks
    chunks = []
    current_chunk = []
    current_chars = 0

    for wt in word_timestamps:
        word = wt.get("word", "")
        start = wt.get("start", 0)
        end = wt.get("end", 0)

        current_chunk.append({"word": word, "start": start, "end": end})
        current_chars += len(word) + 1

        if (current_chars >= cfg["max_chars_per_line"]
                or word.rstrip().endswith((".", "!", "?"))
                or len(current_chunk) >= 6):
            chunks.append(current_chunk)
            current_chunk = []
            current_chars = 0

    if current_chunk:
        chunks.append(current_chunk)

    # Write SRT file
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, chunk in enumerate(chunks, 1):
            start_time = _seconds_to_srt_time(chunk[0]["start"])
            end_time = _seconds_to_srt_time(chunk[-1]["end"])
            text = " ".join(w["word"] for w in chunk)
            f.write(f"{idx}\n{start_time} --> {end_time}\n{text}\n\n")

    return output_path


# ─── Video Assembly (FFmpeg) ─────────────────────────────────────────

def assemble_video(clips_dir, audio_path, srt_path, output_path, bg_music_path=None):
    """
    Assemble final video: stock clips + narration audio + SRT subtitles.
    Uses the 'subtitles' filter (libass) which works on all platforms.
    """
    # Check FFmpeg availability
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: FFmpeg not found. Install it: brew install ffmpeg")
        sys.exit(1)

    # Get audio duration
    probe = subprocess.run(
        ["ffprobe", "-i", audio_path, "-show_entries", "format=duration",
         "-v", "quiet", "-of", "csv=p=0"],
        capture_output=True, text=True
    )
    audio_duration = float(probe.stdout.strip())

    # List all raw clip files
    raw_clips = sorted(Path(clips_dir).glob("*.mp4"))
    if not raw_clips:
        print("ERROR: No clip files found in", clips_dir)
        sys.exit(1)

    # Step 1a: Normalize every clip to identical format (codec, resolution, fps, pixel format)
    # This is REQUIRED — concat demuxer freezes if clips differ in any of these
    norm_dir = Path(clips_dir) / "normalized"
    norm_dir.mkdir(exist_ok=True)
    norm_clips = []

    print(f"  Normalizing {len(raw_clips)} clips to 1920x1080 @ 30fps...")
    for i, clip in enumerate(raw_clips):
        norm_path = norm_dir / f"norm_{i:03d}.mp4"
        cmd_norm = [
            "ffmpeg", "-y", "-i", str(clip),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-an",
            str(norm_path)
        ]
        result = subprocess.run(cmd_norm, capture_output=True, text=True)
        if result.returncode == 0 and norm_path.exists():
            norm_clips.append(norm_path)
        else:
            print(f"  WARNING: Failed to normalize {clip.name}: {result.stderr[-200:]}")

    if not norm_clips:
        print("ERROR: All clip normalizations failed")
        sys.exit(1)

    # Get actual duration of each normalized clip
    clip_durations = {}
    for clip in norm_clips:
        try:
            p = subprocess.run(
                ["ffprobe", "-i", str(clip), "-show_entries", "format=duration",
                 "-v", "quiet", "-of", "csv=p=0"],
                capture_output=True, text=True
            )
            clip_durations[clip] = float(p.stdout.strip())
        except (ValueError, Exception):
            clip_durations[clip] = 5.0

    total_clip_pool = sum(clip_durations.values())
    print(f"  Stock footage pool: {total_clip_pool:.1f}s across {len(norm_clips)} clips")
    print(f"  Audio duration: {audio_duration:.1f}s")

    # Step 1b: Build concat list, looping normalized clips until we cover audio + 20% buffer
    concat_file = Path(clips_dir) / "concat.txt"
    total_clip_duration = 0
    target_duration = audio_duration * 1.2

    with open(concat_file, "w") as f:
        loop_count = 0
        while total_clip_duration < target_duration:
            for clip in norm_clips:
                if total_clip_duration >= target_duration:
                    break
                f.write(f"file '{clip.resolve()}'\n")
                total_clip_duration += clip_durations.get(clip, 5.0)
            loop_count += 1
            if loop_count > 20:
                break

    print(f"  Concat plan: {total_clip_duration:.1f}s of footage ({loop_count} loop(s))")

    # Step 1c: Concatenate normalized clips (now safe — all identical format)
    concat_video = Path(clips_dir) / "concat.mp4"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-t", str(audio_duration),
        "-c:v", "copy",
        "-an",
        str(concat_video)
    ]
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: Concat failed:\n{result.stderr[-500:]}")
        sys.exit(1)

    # Step 2: Merge video + audio + subtitles
    # Build the subtitle filter string (yellow border + black shadow = 3D look)
    sub_filter = ""
    if srt_path and Path(srt_path).exists():
        escaped_srt = str(srt_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        font_dir = str(FONT_PATH.parent) if FONT_PATH.exists() else ""
        # ASS colour format: &HAABBGGRR
        # Yellow #FFD700 → &H0000D7FF  |  Black → &H00000000
        style_parts = [
            f"FontName={SUBTITLE_CONFIG['font_family']}",
            f"FontSize={SUBTITLE_CONFIG['font_size']}",
            "PrimaryColour=&H00000000",       # black text
            "OutlineColour=&H0000D7FF",       # yellow border (FFD700 in BGR)
            f"Outline={SUBTITLE_CONFIG['outline_width']}",
            "BackColour=&H00000000",          # black shadow
            "Shadow=2",                       # shadow depth for 3D feel
            "BorderStyle=1",                  # outline + drop shadow (NOT opaque box)
            f"MarginV={SUBTITLE_CONFIG['margin_bottom']}",
            "Alignment=2",                    # bottom center
            "Bold=1",
        ]
        style_str = ",".join(style_parts)
        if font_dir:
            sub_filter = f"subtitles={escaped_srt}:fontsdir={font_dir}:force_style='{style_str}'"
        else:
            sub_filter = f"subtitles={escaped_srt}:force_style='{style_str}'"
    else:
        print("  No subtitles to burn (SRT file missing or empty)")

    # Build final command
    cmd_final = [
        "ffmpeg", "-y",
        "-i", str(concat_video),
        "-i", audio_path,
    ]

    if bg_music_path and Path(bg_music_path).exists():
        cmd_final.extend(["-i", bg_music_path])

    # Video filter: burn subtitles via -vf (works with -map)
    if sub_filter:
        cmd_final.extend(["-vf", sub_filter])

    # Audio handling
    if bg_music_path and Path(bg_music_path).exists():
        # Mix narration (full volume) + background music (10% volume)
        cmd_final.extend([
            "-filter_complex", "[1:a]volume=1.0[narr];[2:a]volume=0.1[music];[narr][music]amix=inputs=2:duration=first[aout]",
            "-map", "0:v", "-map", "[aout]",
        ])
    else:
        # Simple: video from input 0, audio from input 1
        cmd_final.extend(["-map", "0:v", "-map", "1:a"])

    cmd_final.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", str(audio_duration),
        str(output_path)
    ])

    print(f"  FFmpeg command: {' '.join(str(x) for x in cmd_final[:6])}...")
    result = subprocess.run(cmd_final, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: FFmpeg final assembly failed:\n{result.stderr[-500:]}")
        sys.exit(1)

    # Cleanup temp concat video
    concat_video.unlink(missing_ok=True)
    concat_file.unlink(missing_ok=True)

    print(f"Video assembled: {output_path} ({audio_duration:.1f}s)")
    return str(output_path)


# ─── Main Pipeline ───────────────────────────────────────────────────

def create_video(script_path, voice_id="Brian", bg_music=None, output=None):
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
        clips = fetch_stock_clips(footage_queries, count_per_query=3)
        for i, clip in enumerate(clips):
            clip_path = clips_dir / f"clip_{i:03d}.mp4"
            print(f"  Downloading: {clip['query']} ({clip['duration']}s)")
            download_clip(clip["url"], str(clip_path))

        # Step 2: Generate narration
        print("\n[2/4] Generating narration via HeyGen TTS...")
        audio_path = str(tmpdir / "narration.mp3")
        narration = generate_narration(script_text, voice_id=voice_id, output_path=audio_path)
        print(f"  Narration: {narration['duration']:.1f}s")

        # Step 3: Generate SRT subtitle file
        print("\n[3/4] Building eye-comfort subtitles (SRT)...")
        word_timestamps = narration.get("word_timestamps", [])
        srt_path = str(tmpdir / "subtitles.srt")
        srt_result = generate_srt_file(word_timestamps, srt_path)
        if srt_result:
            print(f"  Subtitles: {len(word_timestamps)} words → SRT file ready")
        else:
            print("  WARNING: No word timestamps available, subtitles will be skipped")
            srt_path = None

        # Step 4: Assemble video
        print("\n[4/4] Assembling final video...")
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_path = output or f"output/video_{datetime.now().strftime('%Y-%m-%d')}.mp4"

        assemble_video(
            clips_dir=str(clips_dir),
            audio_path=str(audio_path),
            srt_path=srt_path,
            output_path=output_path,
            bg_music_path=bg_music,
        )

    print(f"\nVideo created successfully: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Create a video from a script")
    parser.add_argument("--script", required=True, help="Path to script JSON file")
    parser.add_argument("--voice", default="Brian", help="HeyGen voice name (default: Brian)")
    parser.add_argument("--music", default=None, help="Path to background music file")
    parser.add_argument("--output", default=None, help="Output video file path")
    args = parser.parse_args()

    create_video(args.script, voice_id=args.voice, bg_music=args.music, output=args.output)


if __name__ == "__main__":
    main()
