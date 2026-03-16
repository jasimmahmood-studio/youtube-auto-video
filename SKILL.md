---
name: youtube-auto-video
description: >
  Automates faceless YouTube video production: discovers trending topics via YouTube Data API
  across Geopolitics, Health, Wealth, and Relationship niches, generates scripts with AI,
  creates narration + stock footage videos with eye-comfort subtitles using HeyGen and Pexels,
  then uploads to YouTube via Data API v3. Runs daily on autopilot.
  ALWAYS use this skill when the user wants to: auto-generate YouTube videos from trending topics,
  create faceless YouTube content with AI narration and subtitles, build a daily video pipeline,
  generate video scripts, upload AI videos to YouTube, run a faceless channel on autopilot.
  Also trigger on mentions of "YouTube automation", "auto video", "faceless channel",
  "trending video creator", or "daily video upload".
---

# YouTube Auto Video — Trending Topic to Published Video Pipeline

This skill automates the complete pipeline: discover trending topics → generate script → create video with narration + stock footage + subtitles → upload to YouTube. Runs daily to keep your faceless channel active and growing.

## Prerequisites

Before running, set up API credentials. Read `references/api_setup.md` for detailed setup instructions for each service.

### Required Environment Variables

Set these in a `.env` file in the workspace root:

```
# YouTube Data API v3 (for trending topics + upload)
YOUTUBE_API_KEY=your_api_key                    # For reading trending data
YOUTUBE_CLIENT_ID=your_oauth_client_id          # For upload (OAuth 2.0)
YOUTUBE_CLIENT_SECRET=your_oauth_client_secret
YOUTUBE_REFRESH_TOKEN=your_refresh_token

# HeyGen API (for video generation)
HEYGEN_API_KEY=your_heygen_api_key

# Pexels API (for stock footage — free)
PEXELS_API_KEY=your_pexels_api_key

# OpenAI API (for script generation — or use Claude API)
OPENAI_API_KEY=your_openai_api_key
# OR
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### Cost Breakdown (per video)

| Service         | Cost               | Notes                                      |
|-----------------|--------------------|--------------------------------------------|
| YouTube API     | Free               | 10,000 quota units/day                     |
| Pexels API      | Free               | Unlimited stock footage, no attribution req |
| HeyGen API      | ~$0.01/sec video   | ~$0.60-$1.20 for a 1-2 min video           |
| OpenAI/Claude   | ~$0.02-0.05/script | GPT-4o-mini or Claude Haiku for scripts     |
| **Total/video** | **~$0.65-$1.30**   | ~$20-40/month for daily uploads             |

---

## Workflow Overview

```
1. fetch_trending.py    → Discover trending topics via YouTube Data API
2. generate_script.py   → Create video script with hook, body, CTA
3. create_video.py      → Assemble video: HeyGen narration + Pexels stock footage + subtitles
4. upload_youtube.py    → Upload finished video with optimized title, description, tags
5. run_daily.py         → Orchestrate all steps, run on schedule
```

---

## Step 1: Fetch Trending Topics

Script: `scripts/fetch_trending.py`

**What it does:**
- Queries YouTube Data API v3 for trending/popular videos in target niches
- Filters by relevance to the 4 topic categories: Geopolitics, Health, Wealth, Relationship
- Uses a keyword-matching + category system to classify trending content
- Scores topics by view velocity (views relative to upload age) to find truly viral trends
- Avoids duplicate topics by checking against a `history/topics_used.json` log
- Returns the single best topic per run with metadata (title angle, keywords, category)

**Topic Discovery Strategy:**

The script uses a two-pass approach:
1. **Broad scan**: Pull top 50 trending videos from YouTube (regionCode configurable, default US)
2. **Niche filter**: Match against keyword banks for each category:
   - **Geopolitics**: war, sanctions, diplomacy, NATO, elections, trade war, conflict, summit, treaty, border, geopolitics, coup, alliance
   - **Health**: health, disease, diet, mental health, longevity, fitness, sleep, nutrition, pandemic, wellness, medical, brain, gut
   - **Wealth**: money, investing, stocks, crypto, real estate, passive income, recession, economy, finance, wealth, debt, budget, side hustle
   - **Relationship**: relationship, dating, marriage, divorce, love, breakup, attachment, communication, boundaries, toxic, partner, couples

3. **Score & rank**: Videos are scored by `(view_count / hours_since_upload) * relevance_score`

**Usage:**
```bash
python scripts/fetch_trending.py --category health --region US
python scripts/fetch_trending.py --category all --region US
```

**Output:** `output/trending_topic_YYYY-MM-DD.json`

---

## Step 2: Generate Video Script

Script: `scripts/generate_script.py`

**What it does:**
- Takes the trending topic from Step 1
- Generates a 60-90 second video script optimized for faceless YouTube
- Script structure follows a proven engagement formula:
  1. **Hook** (0-5 sec): Pattern interrupt question or shocking statement
  2. **Context** (5-15 sec): Why this topic matters right now
  3. **Body** (15-70 sec): 3-4 key points with transitions
  4. **CTA** (70-90 sec): Subscribe prompt + engagement question
- Generates matching metadata: title (under 60 chars, curiosity-driven), description (SEO-optimized with keywords), tags (15-20 relevant tags)
- Tone: conversational, authoritative, slightly urgent — works for all 4 niches
- Also generates a subtitle-ready transcript with word-level timestamps placeholder (HeyGen provides actual timestamps)

**Script generation uses AI (configurable):**
- Default: OpenAI GPT-4o-mini (cheapest, fast, good quality)
- Alternative: Claude Haiku via Anthropic API
- The prompt template is in `references/script_prompt_template.md` — you can customize tone, length, and style

**Usage:**
```bash
python scripts/generate_script.py --topic output/trending_topic_2026-03-15.json
python scripts/generate_script.py --topic output/trending_topic_2026-03-15.json --ai claude
```

**Output:** `output/script_YYYY-MM-DD.json` containing:
```json
{
  "title": "Why China's New Move Changes Everything",
  "description": "SEO description with keywords...",
  "tags": ["geopolitics", "china", "trade war", ...],
  "script_text": "Full narration script...",
  "sections": [
    {"type": "hook", "text": "...", "duration_estimate": 5},
    {"type": "context", "text": "...", "duration_estimate": 10},
    {"type": "body", "text": "...", "duration_estimate": 55},
    {"type": "cta", "text": "...", "duration_estimate": 15}
  ],
  "stock_footage_queries": ["china trade meeting", "shipping containers port", "stock market graph"]
}
```

---

## Step 3: Create Video

Script: `scripts/create_video.py`

**What it does:**
This is the core production step. It combines AI narration with stock footage and eye-comfort subtitles.

### 3a. Fetch Stock Footage (Pexels)
- Uses `stock_footage_queries` from the script to search Pexels API
- Downloads 5-8 HD clips (1920x1080, landscape) matching the topic
- Falls back to generic b-roll if specific queries return no results
- Clips are trimmed to 8-12 seconds each

### 3b. Generate Narration (HeyGen)
- Sends the script text to HeyGen's text-to-speech API
- Uses a natural, professional voice (configurable — default: "Matthew" for English)
- Returns an audio file with word-level timestamps for subtitle sync

### 3c. Assemble Video (FFmpeg)
- Composites stock footage clips to match narration duration
- Cross-fade transitions between clips (0.5s dissolve)
- Audio narration layered on top of footage
- Background music (optional, from `assets/bg_music/`) at 10% volume

### 3d. Burn Eye-Comfort Subtitles (FFmpeg)
The subtitle system is designed for comfortable viewing — this is a key differentiator:

- **Font**: Bold sans-serif (Montserrat Bold or similar)
- **Size**: Large enough to read on mobile (font size 24-28 at 1080p)
- **Color**: White text (#FFFFFF) with a dark semi-transparent background box (#000000 at 60% opacity)
- **Position**: Lower third of screen (margin-bottom: 50px)
- **Animation**: Word-by-word highlight — current word turns yellow (#FFD700) as it's spoken
- **Line length**: Max 2 lines, max 42 characters per line — never cramped
- **Timing**: Synced to HeyGen's word-level timestamps for perfect lip-sync feel

The subtitle rendering uses FFmpeg's `drawtext` filter with ASS subtitle formatting for the highlight effect.

**Usage:**
```bash
python scripts/create_video.py --script output/script_2026-03-15.json
python scripts/create_video.py --script output/script_2026-03-15.json --voice "Sara" --music assets/bg_music/ambient1.mp3
```

**Output:** `output/video_YYYY-MM-DD.mp4` (1080p, H.264, AAC audio)

---

## Step 4: Upload to YouTube

Script: `scripts/upload_youtube.py`

**What it does:**
- Authenticates via OAuth 2.0 using stored refresh token
- Uploads the video with optimized metadata from the script generation step
- Sets: title, description, tags, category, thumbnail (auto-generated), privacy status
- Default privacy: `public` (configurable to `private` or `unlisted` for review)
- Schedules publish time if `--schedule` flag is used (optimal: 2-4 PM EST for US audience)
- Logs the uploaded video URL and ID to `history/uploads.json`

**YouTube metadata optimization:**
- Title: Under 60 chars, includes primary keyword, curiosity gap
- Description: First 150 chars are SEO-critical (shown in search), includes timestamps, hashtags
- Tags: 15-20 tags mixing broad and specific keywords
- Category: Maps to YouTube category IDs (News=25, Education=27, Entertainment=24, People=22)

**Usage:**
```bash
python scripts/upload_youtube.py --video output/video_2026-03-15.mp4 --metadata output/script_2026-03-15.json
python scripts/upload_youtube.py --video output/video_2026-03-15.mp4 --metadata output/script_2026-03-15.json --privacy unlisted
```

---

## Step 5: Daily Orchestrator

Script: `scripts/run_daily.py`

**What it does:**
- Runs all 4 steps in sequence with error handling at each stage
- Rotates through topic categories daily: Mon=Geopolitics, Tue=Health, Wed=Wealth, Thu=Relationship, Fri-Sun=highest-trending-any
- Saves a daily run log to `logs/run_YYYY-MM-DD.json`
- Cleans up temp files after successful upload
- Sends summary to console (video URL, topic, category, duration, cost estimate)

**Usage:**
```bash
# Single run
python scripts/run_daily.py

# Dry run (generates everything but doesn't upload)
python scripts/run_daily.py --dry-run

# Schedule as daily cron at 10:00 AM
python scripts/run_daily.py --schedule

# Force a specific category
python scripts/run_daily.py --category geopolitics
```

---

## Running for the First Time

1. Install dependencies:
   ```bash
   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 \
       requests python-dotenv openai anthropic pexels-api --break-system-packages
   ```

2. Install FFmpeg (required for video assembly):
   ```bash
   sudo apt-get install ffmpeg -y    # Linux
   brew install ffmpeg               # macOS
   ```

3. Download subtitle font:
   ```bash
   python scripts/setup_fonts.py     # Downloads Montserrat Bold to assets/fonts/
   ```

4. Set up `.env` file with all credentials (see Prerequisites above)

5. Run the OAuth flow for YouTube upload (one-time):
   ```bash
   python scripts/youtube_auth.py    # Opens browser for Google OAuth consent
   ```

6. Test the full pipeline with dry run:
   ```bash
   python scripts/run_daily.py --dry-run
   ```

7. Run for real:
   ```bash
   python scripts/run_daily.py
   ```

8. Schedule daily:
   ```bash
   python scripts/run_daily.py --schedule
   ```

---

## Customization

### Change Voice
Edit `.env` or pass `--voice` flag. HeyGen voices: Matthew (default, male), Sara (female), Josh (deep male). See `references/heygen_voices.md` for full list.

### Change Video Length
Edit `references/script_prompt_template.md` — adjust the target duration in the prompt. Default is 60-90 seconds (optimal for faceless channels starting out).

### Add/Remove Topic Categories
Edit the keyword banks in `scripts/fetch_trending.py` under the `TOPIC_KEYWORDS` dictionary.

### Change Subtitle Style
Edit the subtitle config in `scripts/create_video.py` under `SUBTITLE_CONFIG`. You can change font, size, colors, position, and animation style. Pre-built styles are documented in `references/subtitle_styles.md` — including a "MrBeast/Shorts Style" with Impact font, center positioning, red highlights, and `all_caps: True` for bold uppercase text. When switching styles, always check whether `all_caps` should be enabled — it's critical for high-energy styles like MrBeast's.

---

## Troubleshooting

- **YouTube quota exceeded**: YouTube Data API has 10,000 units/day. Trending fetch uses ~100 units, upload uses ~1,600 units. You have room for ~5-6 uploads/day.
- **HeyGen timeout**: Long scripts (>2 min narration) may timeout. Keep scripts under 90 seconds.
- **FFmpeg not found**: Make sure FFmpeg is installed and on your PATH.
- **Pexels returns no clips**: The query was too specific. The script auto-falls back to broader terms.
- **YouTube upload fails with 403**: Your OAuth token expired. Re-run `scripts/youtube_auth.py`.
- **Subtitles out of sync**: HeyGen's word timestamps occasionally drift. The script includes a ±0.1s tolerance and auto-adjusts.

## Reference Files

- `references/api_setup.md` — Step-by-step setup for all 4 APIs (YouTube, HeyGen, Pexels, OpenAI)
- `references/script_prompt_template.md` — The AI prompt used to generate video scripts (editable)
- `references/heygen_voices.md` — Available HeyGen voices with samples
- `references/subtitle_styles.md` — Subtitle configuration options and examples
