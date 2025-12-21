# Video-to-Action-Plan

Record a screen video, point at UI elements while talking, get a structured task list.

## How It Works

```
Record Video → Whisper Transcribes → Extract Frames at "this/that/here" → Claude Analyzes → Action Plan
```

1. **You record** a screen video while talking: *"This button should be blue"*
2. **Whisper** transcribes with word-level timestamps (local, free)
3. **Script extracts frames** when you say "this", "that", "here", etc.
4. **Claude API** analyzes frames + transcript → structured issues list
5. **Output** to stdout (or NOTES.md file)

## Quick Start

### 1. Install Dependencies

```bash
# FFmpeg
winget install ffmpeg          # Windows
brew install ffmpeg            # Mac
sudo apt install ffmpeg        # Linux

# Python packages
pip install openai-whisper anthropic
```

### 2. Set API Key

```bash
# Option A: Environment variable
export ANTHROPIC_API_KEY=sk-ant-...

# Option B: File
echo "sk-ant-..." > ~/.anthropic_api_key
```

### 3. Run

```bash
# Process a specific video
python quick_notes.py video.mp4

# Process latest video from a folder
python quick_notes.py --watch-dir ~/Videos

# Specify output location
python quick_notes.py video.mp4 -o ./notes
```

## Example Output

```markdown
## Issues Found

### 1. Button Color Change
- **Element**: "Submit" button
- **Location**: Bottom right of form
- **Issue**: Currently gray, hard to see
- **Fix**: Change to blue (#0066CC)

### 2. Text Alignment
- **Element**: Header text
- **Location**: Top of page
- **Issue**: Left-aligned, looks off-center
- **Fix**: Center-align the header

## Summary
Two UI changes needed: make submit button blue and center the header.
```

## Claude Code Integration

Add to `~/.claude/settings.json` for zero-click automation:

```json
{
  "permissions": {
    "allow": [
      "Bash(python /path/to/quick_notes.py:*)"
    ]
  }
}
```

Then just say: *"Run quick_notes.py and create a plan"*

## Cost

| Component | Cost |
|-----------|------|
| Whisper | Free (runs locally) |
| Claude API | ~$0.02-0.05 per video |

Typical video uses ~3-5K input tokens (transcript + 15 images) and ~500-1K output tokens.

## Requirements

- Python 3.10+
- FFmpeg
- Anthropic API key

## License

MIT
