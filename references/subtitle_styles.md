# Subtitle Styles — Eye Comfort Configuration

The subtitle system is designed for comfortable, extended viewing. Research shows that subtitle readability directly impacts watch time.

## Default Style (Recommended)

```python
SUBTITLE_CONFIG = {
    "font_family": "Montserrat-Bold",
    "font_size": 26,                    # px at 1080p — readable on mobile
    "primary_color": "#FFFFFF",          # White for current text
    "highlight_color": "#FFD700",        # Gold yellow for active word
    "background_color": "#000000",       # Black background box
    "background_opacity": 0.6,          # 60% opacity — readable without blocking video
    "position": "bottom",               # Lower third
    "margin_bottom": 50,                # px from bottom edge
    "max_chars_per_line": 42,           # Prevents cramped text
    "max_lines": 2,                     # Never more than 2 lines
    "word_highlight": True,             # Word-by-word color change as spoken
    "outline_color": "#000000",         # Black text outline
    "outline_width": 2,                 # px — ensures readability on bright footage
}
```

## Why These Choices

**Font (Montserrat Bold)**: Sans-serif is easier to read on screens. Bold weight ensures visibility at smaller sizes. Montserrat is free (Google Fonts), widely available, and has excellent legibility.

**Size (26px)**: YouTube recommends subtitles be at least 22px at 1080p. 26px adds margin for mobile viewers where the screen is smaller.

**White + Gold highlight**: High contrast on dark backgrounds. The gold highlight for the active word helps viewers track along — especially useful for non-native English speakers and accessibility.

**60% opacity background**: A fully opaque box hides too much video. No box makes text unreadable on bright footage. 60% is the sweet spot based on YouTube accessibility guidelines.

**Max 42 chars/line, 2 lines**: Netflix subtitle guidelines use 42 characters. This prevents the eye from having to scan too far horizontally. Two lines max prevents the subtitle area from dominating the screen.

## Alternative Styles

### Style: "Clean Minimal"
```python
SUBTITLE_CONFIG = {
    "font_family": "Montserrat-Bold",
    "font_size": 28,
    "primary_color": "#FFFFFF",
    "highlight_color": "#00FF88",        # Green highlight
    "background_color": "none",          # No background box
    "outline_color": "#000000",
    "outline_width": 3,                  # Thicker outline to compensate for no background
    "word_highlight": True,
}
```

### Style: "MrBeast/Shorts Style"
```python
SUBTITLE_CONFIG = {
    "font_family": "Impact",
    "font_size": 36,                     # Large, attention-grabbing
    "primary_color": "#FFFFFF",
    "highlight_color": "#FF0000",        # Red highlight
    "background_color": "none",
    "outline_color": "#000000",
    "outline_width": 4,
    "position": "center",               # Center of screen
    "word_highlight": True,
    "all_caps": True,                    # UPPERCASE for emphasis
}
```

## FFmpeg Implementation

The subtitles are rendered using FFmpeg's `drawtext` filter chain. Each word gets its own drawtext entry with precise start/end timestamps from HeyGen's word-level timing data.

```bash
# Simplified example of the FFmpeg subtitle filter
ffmpeg -i video.mp4 -vf "
  drawtext=text='This':fontfile=Montserrat-Bold.ttf:fontsize=26:
    fontcolor=white:borderw=2:bordercolor=black:
    x=(w-text_w)/2:y=h-70:
    enable='between(t,0.0,0.3)',
  drawtext=text='is':fontfile=Montserrat-Bold.ttf:fontsize=26:
    fontcolor=gold:borderw=2:bordercolor=black:
    x=(w-text_w)/2:y=h-70:
    enable='between(t,0.3,0.5)'
" -codec:a copy output_with_subs.mp4
```

The actual implementation in `create_video.py` generates this filter chain dynamically from the word timestamps.
