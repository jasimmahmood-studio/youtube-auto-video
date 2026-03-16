# API Setup Guide

## 1. YouTube Data API v3

You need two things: an API key (for reading trending data) and OAuth 2.0 credentials (for uploading).

### API Key (for trending topics)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Go to **APIs & Services > Library**
4. Search for "YouTube Data API v3" and enable it
5. Go to **APIs & Services > Credentials**
6. Click **Create Credentials > API Key**
7. Copy the key → set as `YOUTUBE_API_KEY` in `.env`

### OAuth 2.0 (for video upload)

1. In the same project, go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth 2.0 Client ID**
3. Application type: **Desktop app**
4. Download the JSON → save as `client_secrets.json` in project root
5. Set `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` in `.env`
6. Run `python scripts/youtube_auth.py` — this opens a browser for consent
7. After consent, the script saves a refresh token → set as `YOUTUBE_REFRESH_TOKEN`

**Important**: Your app starts in "Testing" mode, limited to 100 users. For personal use this is fine. For production, submit for verification.

**Quota**: 10,000 units/day free. Trending fetch ≈ 100 units. Upload ≈ 1,600 units. Plenty for daily use.

---

## 2. HeyGen API

HeyGen generates the AI narration audio (text-to-speech with word timestamps).

1. Sign up at [heygen.com](https://www.heygen.com/)
2. Go to **Settings > API**
3. Generate an API key
4. Set as `HEYGEN_API_KEY` in `.env`

**Pricing**: Pay-as-you-go at ~$0.01/second of video. A 90-second narration costs ~$0.90.

**Rate limits**: 60 requests/minute on the API. More than enough for daily use.

**Alternative**: If HeyGen is too expensive, you can swap in ElevenLabs ($5/mo for 30 min audio) by modifying `scripts/create_video.py` to use ElevenLabs TTS instead.

---

## 3. Pexels API

Pexels provides free stock video footage. No attribution required for API use.

1. Sign up at [pexels.com](https://www.pexels.com/)
2. Go to **Image & Video API** in your account
3. Request API access (instant approval)
4. Copy your API key → set as `PEXELS_API_KEY` in `.env`

**Limits**: 200 requests/hour, 20,000/month. We use 5-8 requests per video — never an issue.

**Alternatives**: Pixabay API (also free, requires attribution) or Videvo.

---

## 4. OpenAI API (for script generation)

Used to generate the video script from the trending topic.

1. Sign up at [platform.openai.com](https://platform.openai.com/)
2. Go to **API Keys** and create a new key
3. Set as `OPENAI_API_KEY` in `.env`

**Model**: GPT-4o-mini is the default (cheapest at ~$0.15/1M input tokens). Override with `--ai-model gpt-4o` for better quality.

**Alternative**: Set `ANTHROPIC_API_KEY` instead and use `--ai claude` flag. Uses Claude Haiku by default.

---

## 5. Alternative: Anthropic API (for script generation)

1. Sign up at [console.anthropic.com](https://console.anthropic.com/)
2. Go to **API Keys** and create a new key
3. Set as `ANTHROPIC_API_KEY` in `.env`
4. Use `--ai claude` flag when running scripts
