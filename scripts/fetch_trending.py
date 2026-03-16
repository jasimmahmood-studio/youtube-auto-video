#!/usr/bin/env python3
"""
Fetch trending YouTube topics filtered by niche categories.
Uses YouTube Data API v3 to discover viral content in Geopolitics, Health, Wealth, Relationship niches.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Keyword banks for niche filtering
TOPIC_KEYWORDS = {
    "geopolitics": [
        "war", "sanctions", "diplomacy", "nato", "elections", "trade war", "conflict",
        "summit", "treaty", "border", "geopolitics", "coup", "alliance", "missile",
        "military", "invasion", "ceasefire", "embargo", "nuclear", "territory",
        "annexation", "rebellion", "protest", "regime", "dictator", "democracy",
        "united nations", "security council", "foreign policy", "cold war"
    ],
    "health": [
        "health", "disease", "diet", "mental health", "longevity", "fitness", "sleep",
        "nutrition", "pandemic", "wellness", "medical", "brain", "gut", "immune",
        "cancer", "diabetes", "anxiety", "depression", "exercise", "weight loss",
        "fasting", "supplement", "vaccine", "virus", "hormone", "aging", "metabolism",
        "inflammation", "microbiome", "dopamine", "cortisol"
    ],
    "wealth": [
        "money", "investing", "stocks", "crypto", "real estate", "passive income",
        "recession", "economy", "finance", "wealth", "debt", "budget", "side hustle",
        "millionaire", "billionaire", "savings", "retirement", "inflation", "interest rate",
        "federal reserve", "market crash", "bitcoin", "earnings", "revenue", "profit",
        "startup", "entrepreneur", "business", "income", "trading"
    ],
    "relationship": [
        "relationship", "dating", "marriage", "divorce", "love", "breakup", "attachment",
        "communication", "boundaries", "toxic", "partner", "couples", "romance",
        "cheating", "trust", "intimacy", "loneliness", "self-love", "narcissist",
        "red flag", "green flag", "situationship", "heartbreak", "compatibility",
        "emotional intelligence", "vulnerability", "commitment"
    ]
}

# YouTube category IDs that align with our niches
RELEVANT_CATEGORY_IDS = [
    "22",  # People & Blogs
    "24",  # Entertainment
    "25",  # News & Politics
    "26",  # Howto & Style
    "27",  # Education
    "28",  # Science & Technology
]


def get_trending_videos(region_code="US", max_results=50):
    """Fetch trending videos from YouTube."""
    if not YOUTUBE_API_KEY:
        print("ERROR: YOUTUBE_API_KEY not set in .env file")
        sys.exit(1)

    url = f"{YOUTUBE_API_BASE}/videos"
    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"ERROR: YouTube API returned {response.status_code}: {response.text}")
        sys.exit(1)

    return response.json().get("items", [])


def search_niche_videos(category, region_code="US", max_results=25):
    """Search YouTube for recent popular videos in a specific niche."""
    if not YOUTUBE_API_KEY:
        print("ERROR: YOUTUBE_API_KEY not set in .env file")
        sys.exit(1)

    keywords = TOPIC_KEYWORDS.get(category, [])
    # Pick 3-5 high-signal keywords to search
    search_query = " | ".join(keywords[:5])

    url = f"{YOUTUBE_API_BASE}/search"
    params = {
        "part": "snippet",
        "q": search_query,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": _days_ago_iso(7),
        "regionCode": region_code,
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"ERROR: YouTube search API returned {response.status_code}: {response.text}")
        return []

    # Get video IDs and fetch full details
    video_ids = [item["id"]["videoId"] for item in response.json().get("items", [])]
    if not video_ids:
        return []

    return _get_video_details(video_ids)


def _get_video_details(video_ids):
    """Fetch full video details for a list of video IDs."""
    url = f"{YOUTUBE_API_BASE}/videos"
    params = {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(video_ids),
        "key": YOUTUBE_API_KEY,
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return []
    return response.json().get("items", [])


def _days_ago_iso(days):
    """Return ISO format datetime for N days ago."""
    from datetime import timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def calculate_relevance_score(video, category):
    """Score how relevant a video is to a niche category."""
    keywords = TOPIC_KEYWORDS.get(category, [])
    title = video["snippet"]["title"].lower()
    description = video["snippet"].get("description", "").lower()
    tags = [t.lower() for t in video["snippet"].get("tags", [])]

    score = 0
    matched_keywords = []

    for keyword in keywords:
        kw = keyword.lower()
        if kw in title:
            score += 3  # Title match is strongest signal
            matched_keywords.append(keyword)
        elif kw in description[:500]:
            score += 1.5  # Description match
            matched_keywords.append(keyword)
        elif any(kw in tag for tag in tags):
            score += 1  # Tag match
            matched_keywords.append(keyword)

    return score, list(set(matched_keywords))


def calculate_virality_score(video):
    """Score based on view velocity (views per hour since upload)."""
    stats = video.get("statistics", {})
    view_count = int(stats.get("viewCount", 0))
    like_count = int(stats.get("likeCount", 0))

    published = video["snippet"]["publishedAt"]
    pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    hours_since = max(1, (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600)

    view_velocity = view_count / hours_since
    engagement_ratio = like_count / max(1, view_count)

    # Combined score: view velocity weighted by engagement
    return view_velocity * (1 + engagement_ratio * 10)


def load_used_topics():
    """Load previously used topics to avoid duplicates."""
    history_file = Path("history/topics_used.json")
    if history_file.exists():
        with open(history_file) as f:
            return json.load(f)
    return []


def save_topic_to_history(topic):
    """Save a topic to history to prevent reuse."""
    history_dir = Path("history")
    history_dir.mkdir(exist_ok=True)
    history_file = history_dir / "topics_used.json"

    history = load_used_topics()
    history.append({
        "title": topic["title"],
        "category": topic["category"],
        "date": datetime.now().strftime("%Y-%m-%d"),
        "video_id": topic["source_video_id"],
    })
    # Keep last 90 days of history
    history = history[-90:]

    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)


def find_best_topic(category="all", region_code="US"):
    """Main function: find the best trending topic for a given category."""
    used_topics = load_used_topics()
    used_titles = {t["title"].lower() for t in used_topics}

    candidates = []

    if category == "all":
        categories = list(TOPIC_KEYWORDS.keys())
    else:
        categories = [category]

    for cat in categories:
        # Two sources: trending page + niche search
        trending = get_trending_videos(region_code, max_results=50)
        niche = search_niche_videos(cat, region_code, max_results=25)

        all_videos = trending + niche

        for video in all_videos:
            title = video["snippet"]["title"]
            if title.lower() in used_titles:
                continue  # Skip already-used topics

            relevance_score, matched_keywords = calculate_relevance_score(video, cat)
            if relevance_score < 2:
                continue  # Not relevant enough

            virality_score = calculate_virality_score(video)
            combined_score = virality_score * (relevance_score / 10)

            candidates.append({
                "title": title,
                "description": video["snippet"].get("description", "")[:500],
                "category": cat,
                "source_video_id": video["id"] if isinstance(video["id"], str) else video["id"].get("videoId", ""),
                "channel": video["snippet"].get("channelTitle", ""),
                "view_count": int(video.get("statistics", {}).get("viewCount", 0)),
                "like_count": int(video.get("statistics", {}).get("likeCount", 0)),
                "published_at": video["snippet"]["publishedAt"],
                "matched_keywords": matched_keywords,
                "relevance_score": relevance_score,
                "virality_score": round(virality_score, 2),
                "combined_score": round(combined_score, 2),
            })

    if not candidates:
        print(f"WARNING: No suitable topics found for category '{category}'")
        return None

    # Sort by combined score and return the best
    candidates.sort(key=lambda x: x["combined_score"], reverse=True)
    best = candidates[0]

    print(f"Selected topic: {best['title']}")
    print(f"Category: {best['category']} | Score: {best['combined_score']}")
    print(f"Keywords: {', '.join(best['matched_keywords'])}")

    return best


def main():
    parser = argparse.ArgumentParser(description="Fetch trending YouTube topics by niche")
    parser.add_argument("--category", default="all",
                        choices=["all", "geopolitics", "health", "wealth", "relationship"],
                        help="Topic category to fetch (default: all)")
    parser.add_argument("--region", default="US", help="YouTube region code (default: US)")
    parser.add_argument("--output", default=None, help="Output file path (default: output/trending_topic_DATE.json)")
    args = parser.parse_args()

    topic = find_best_topic(category=args.category, region_code=args.region)

    if topic is None:
        print("No suitable topic found. Try a different category or region.")
        sys.exit(1)

    # Save output
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_file = args.output or f"output/trending_topic_{datetime.now().strftime('%Y-%m-%d')}.json"

    with open(output_file, "w") as f:
        json.dump(topic, f, indent=2)

    print(f"Saved to {output_file}")
    save_topic_to_history(topic)


if __name__ == "__main__":
    main()
