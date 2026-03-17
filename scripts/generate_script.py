#!/usr/bin/env python3
"""
Generate a YouTube video script from a trending topic using AI.
Supports OpenAI (GPT-4o-mini) and Anthropic (Claude Haiku) as backends.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Load the prompt template
SCRIPT_DIR = Path(__file__).parent.parent
PROMPT_TEMPLATE_PATH = SCRIPT_DIR / "references" / "script_prompt_template.md"


def load_prompt_template():
    """Load and parse the prompt template from references."""
    if not PROMPT_TEMPLATE_PATH.exists():
        # Fallback inline template
        return {
            "system": (
                "You are a professional YouTube scriptwriter specializing in faceless narration-style videos. "
                "You write scripts that are engaging, informative, and optimized for audience retention. "
                "Your tone is conversational but authoritative. You never use filler phrases like 'In this video'. "
                "IMPORTANT: You MUST write everything in English only. Never use Hindi, Arabic, or any other language. "
                "All titles, descriptions, tags, and scripts must be in English."
            ),
            "user_template": (
                "Write a YouTube video script about: {topic_title}\n\n"
                "Context: {topic_description}\n"
                "Category: {category}\n"
                "Target duration: 60-90 seconds (~100-135 words)\n\n"
                "Structure: HOOK (5s) → CONTEXT (10s) → BODY with 3-4 points (55s) → CTA (15s)\n\n"
                "Generate title (under 60 chars, curiosity-driven), description (150 words, SEO-optimized), "
                "tags (15-20), script_text, sections array, and stock_footage_queries (5-8 Pexels search terms).\n\n"
                "CRITICAL: Everything MUST be in English. Return ONLY valid JSON (no markdown, no code fences) "
                "with keys: title, description, tags, script_text, sections, stock_footage_queries"
            )
        }

    content = PROMPT_TEMPLATE_PATH.read_text()

    # Extract system and user prompts from the markdown
    system_prompt = ""
    user_template = ""

    if "## System Prompt" in content and "## User Prompt Template" in content:
        system_section = content.split("## System Prompt")[1].split("## User Prompt Template")[0]
        user_section = content.split("## User Prompt Template")[1].split("## Customization")[0] if "## Customization" in content else content.split("## User Prompt Template")[1]

        # Extract content between code fences
        for section, var_name in [(system_section, "system"), (user_section, "user")]:
            lines = section.strip().split("\n")
            in_code = False
            extracted = []
            for line in lines:
                if line.strip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code:
                    extracted.append(line)
            text = "\n".join(extracted).strip()
            if var_name == "system":
                system_prompt = text
            else:
                user_template = text

    return {"system": system_prompt, "user_template": user_template}


def generate_with_openai(topic, system_prompt, user_prompt, model="gpt-4o-mini"):
    """Generate script using OpenAI API."""
    try:
        import openai
    except ImportError:
        print("ERROR: openai package not installed. Run: pip install openai --break-system-packages")
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in .env file")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
        max_tokens=2000,
    )

    return response.choices[0].message.content


def generate_with_claude(topic, system_prompt, user_prompt, model="claude-haiku-4-5-20251001"):
    """Generate script using Anthropic Claude API."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic --break-system-packages")
        sys.exit(1)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env file")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt + "\n\nRespond with valid JSON only, no markdown."},
        ],
    )

    return response.content[0].text


def parse_script_response(raw_response):
    """Parse and validate the AI-generated script JSON."""
    # Try to parse JSON
    try:
        # Handle potential markdown code fences
        text = raw_response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
        script_data = json.loads(text)
    except json.JSONDecodeError as e:
        # Try to repair truncated JSON by closing open strings/arrays/objects
        print(f"WARNING: JSON parse failed ({e}), attempting repair...")
        repaired = text.rstrip()
        # Close any unterminated string
        if repaired.count('"') % 2 != 0:
            repaired += '"'
        # Close any open arrays/objects
        open_brackets = repaired.count('[') - repaired.count(']')
        open_braces = repaired.count('{') - repaired.count('}')
        repaired += ']' * max(0, open_brackets)
        repaired += '}' * max(0, open_braces)
        try:
            script_data = json.loads(repaired)
            print("  JSON repair succeeded")
        except json.JSONDecodeError:
            print(f"ERROR: Failed to parse AI response as JSON even after repair")
            print(f"Raw response: {raw_response[:500]}")
            sys.exit(1)

    # Validate required fields
    required_fields = ["title", "description", "tags", "script_text", "sections", "stock_footage_queries"]
    missing = [f for f in required_fields if f not in script_data]
    if missing:
        print(f"WARNING: Missing fields in script: {missing}")
        # Fill defaults for missing fields
        defaults = {
            "title": "Untitled Video",
            "description": "",
            "tags": [],
            "script_text": "",
            "sections": [],
            "stock_footage_queries": [],
        }
        for field in missing:
            script_data[field] = defaults.get(field, "")

    # Validate title length
    if len(script_data["title"]) > 100:
        script_data["title"] = script_data["title"][:97] + "..."

    # Ensure tags is a list
    if isinstance(script_data["tags"], str):
        script_data["tags"] = [t.strip() for t in script_data["tags"].split(",")]

    # Count words for duration estimate
    word_count = len(script_data["script_text"].split())
    script_data["estimated_duration_seconds"] = round(word_count / 2.5)  # ~150 wpm = 2.5 wps
    script_data["word_count"] = word_count

    return script_data


def main():
    parser = argparse.ArgumentParser(description="Generate a YouTube video script from a trending topic")
    parser.add_argument("--topic", required=True, help="Path to trending topic JSON file")
    parser.add_argument("--ai", default="claude", choices=["openai", "claude"],
                        help="AI backend to use (default: claude)")
    parser.add_argument("--ai-model", default=None,
                        help="Override AI model (default: gpt-4o-mini for openai, claude-haiku for claude)")
    parser.add_argument("--output", default=None, help="Output file path")
    args = parser.parse_args()

    # Load topic
    topic_path = Path(args.topic)
    if not topic_path.exists():
        print(f"ERROR: Topic file not found: {args.topic}")
        sys.exit(1)

    with open(topic_path) as f:
        topic = json.load(f)

    print(f"Generating script for: {topic['title']}")
    print(f"Category: {topic['category']}")

    # Load prompt template
    prompts = load_prompt_template()

    # Fill in the user prompt
    user_prompt = prompts["user_template"].format(
        topic_title=topic["title"],
        topic_description=topic.get("description", ""),
        category=topic["category"],
    )

    # Generate script
    if args.ai == "openai":
        model = args.ai_model or "gpt-4o-mini"
        print(f"Using OpenAI {model}...")
        raw = generate_with_openai(topic, prompts["system"], user_prompt, model)
    else:
        model = args.ai_model or "claude-haiku-4-5-20251001"
        print(f"Using Claude {model}...")
        raw = generate_with_claude(topic, prompts["system"], user_prompt, model)

    # Parse and validate
    script_data = parse_script_response(raw)

    # Add metadata
    script_data["source_topic"] = topic
    script_data["generated_at"] = datetime.now().isoformat()
    script_data["ai_backend"] = f"{args.ai}/{model}"

    # Save output
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_file = args.output or f"output/script_{datetime.now().strftime('%Y-%m-%d')}.json"

    with open(output_file, "w") as f:
        json.dump(script_data, f, indent=2)

    print(f"\nScript generated successfully!")
    print(f"Title: {script_data['title']}")
    print(f"Duration: ~{script_data['estimated_duration_seconds']}s ({script_data['word_count']} words)")
    print(f"Stock queries: {len(script_data['stock_footage_queries'])} terms")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
