# Detailed Setup Guide

This guide provides comprehensive setup instructions for Video-to-Action-Plan.

## Prerequisites

### Python 3.10+

**Windows:**
```bash
winget install Python.Python.3.12
```

**Mac:**
```bash
brew install python@3.12
```

**Linux:**
```bash
sudo apt install python3.12 python3.12-venv
```

### FFmpeg

**Windows:**
```bash
winget install Gyan.FFmpeg
# Or download from: https://ffmpeg.org/download.html
```

**Mac:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

Verify installation:
```bash
ffmpeg -version
ffprobe -version
```

### Python Dependencies

```bash
pip install openai-whisper anthropic
```

Note: First run of Whisper downloads the model (~140MB for "base").

### Anthropic API Key

Get your key from: https://console.anthropic.com/

**Option A - Environment variable:**
```bash
# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Mac/Linux
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Option B - File:**
```bash
echo "sk-ant-..." > ~/.anthropic_api_key
```

---

## Usage

### Basic Usage

```bash
# Process a specific video
python quick_notes.py video.mp4

# Process latest video from a folder
python quick_notes.py --watch-dir ~/Videos

# Custom output location
python quick_notes.py video.mp4 -o ./my-notes
```

### Command Line Options

```
usage: quick_notes.py [-h] [-w WATCH_DIR] [-o OUTPUT_DIR] [video]

positional arguments:
  video                 Path to video file

options:
  -h, --help            Show help message
  -w, --watch-dir       Folder to find latest MP4 from
  -o, --output-dir      Output directory (default: ./output)
```

---

## Claude Code Integration

For zero-click automation with Claude Code:

### 1. Add Auto-Approve Rule

Edit `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(python /full/path/to/quick_notes.py:*)"
    ]
  }
}
```

Replace `/full/path/to/` with the actual path to your script.

### 2. Use It

Just tell Claude Code:

```
Run quick_notes.py --watch-dir ~/Videos and create a plan from the output
```

The script runs automatically, Claude sees the output, and creates your plan.

---

## Token Usage & Cost

| Component | Tokens | Cost (Sonnet) |
|-----------|--------|---------------|
| Transcript | ~500-2000 | - |
| 15 images | ~1500-3000 | - |
| Output | ~500-1000 | - |
| **Total** | ~2500-6000 | **~$0.02-0.05/video** |

Whisper runs locally (free). Only the Claude API call costs money.

---

## Customization

### Change Trigger Words

Edit `POINTING_WORDS` in `quick_notes.py`:

```python
POINTING_WORDS = [
    "this", "that", "here", "there",
    "click", "select", "change",
    # Add your own words
]
```

### Change AI Model

In `analyze_with_claude()`, change the model:

```python
# Faster & cheaper
model="claude-haiku-3-5-latest"

# Better analysis
model="claude-opus-4-20250514"
```

### Adjust Frame Extraction

The script extracts up to 15 frames. To change:

```python
for i, moment in enumerate(moments[:15]):  # Change 15 to your limit
```

---

## Troubleshooting

### FFmpeg not found

Ensure FFmpeg is in your PATH:
```bash
# Check if installed
which ffmpeg  # Mac/Linux
where ffmpeg  # Windows
```

If not found, add it to PATH or reinstall.

### Whisper slow on first run

First run downloads the model. Subsequent runs are faster.

### "No MP4 files found"

Make sure your `--watch-dir` path is correct and contains `.mp4` files.

### API key not working

1. Check the key is valid at console.anthropic.com
2. Ensure no extra whitespace in the key file
3. Try setting via environment variable instead

### Out of memory

Whisper uses GPU if available. For large videos on low-memory systems:
```bash
# Force CPU mode
export CUDA_VISIBLE_DEVICES=""
python quick_notes.py video.mp4
```

---

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Video     │────▶│   FFmpeg    │────▶│   Whisper   │
│   (.mp4)    │     │ (audio.wav) │     │ (transcript)│
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │  Find words │
                                        │ "this/that" │
                                        └─────────────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Claude Code │◀────│   stdout    │◀────│ Claude API  │
│   (plan)    │     │   (notes)   │     │  (analyze)  │
└─────────────┘     └─────────────┘     └─────────────┘
```

1. **FFmpeg** extracts audio from video
2. **Whisper** transcribes with word-level timestamps
3. **Script** finds "pointing words" and extracts frames at those moments
4. **Claude API** analyzes frames + transcript → structured issue list
5. **Output** goes to stdout and NOTES.md file

---

## License

MIT - Do whatever you want with this.
