# Claude Quick Video Notes

**Record your screen, point at things while talking, get a structured action plan.**

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Mac%20%7C%20Linux-lightgrey)
![AI](https://img.shields.io/badge/AI-Whisper%20%2B%20Claude-purple)

---

## What Is This?

A simple Python script that turns screen recordings into structured notes. Record yourself talking through anything on screen - UI changes, code reviews, bug reports, design feedback, training content - and get organized action items.

**Built by [Reid Havens](https://linkedin.com/in/reid-havens) of [Analytic Endeavors](https://www.analyticendeavors.com)**

---

## How It Works

```
Record Video --> Whisper Transcribes --> Extract Frames at "this/that/here" --> Claude Analyzes --> Action Plan
```

1. **You record** a screen video while talking: *"This button should be blue"* or *"Look at this error message"*
2. **Whisper** transcribes with word-level timestamps (runs locally, free)
3. **Script extracts frames** when you say pointing words ("this", "that", "here", "look", etc.)
4. **Claude API** analyzes frames + transcript --> structured issues list
5. **Output** to stdout and NOTES.md file

---

## Use Cases

| Scenario | Example |
|----------|---------|
| **UI/Design Feedback** | *"This button should be blue, and that spacing is too tight"* |
| **Bug Reports** | *"Look at this error - it happens when I click here"* |
| **Code Reviews** | *"See this function? It needs error handling here"* |
| **Training/Demos** | *"Notice how this workflow goes from here to there"* |
| **Documentation** | *"This screen shows the settings, that one shows results"* |
| **QA Testing** | *"Watch what happens when I click this - that's wrong"* |

If you can point at it and talk about it, this tool captures it.

---

## Quick Start

### 1. Install Dependencies

```bash
# FFmpeg (required for video processing)
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

---

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

---

## Claude Code Integration

For zero-click automation with [Claude Code](https://claude.com/claude-code):

Add to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(python /path/to/quick_notes.py:*)"
    ]
  }
}
```

Then just say: *"Run quick_notes.py --watch-dir ~/Videos and create a plan from the output"*

The script runs automatically, Claude sees the output, and creates your plan.

---

## Cost & Performance

| Component | Cost | Notes |
|-----------|------|-------|
| **Whisper** | Free | Runs locally on your machine |
| **Claude API** | ~$0.02-0.05/video | ~3-5K input tokens (transcript + 15 images) |
| **Total** | **~$0.02-0.05** | Per video processed |

First run downloads the Whisper model (~140MB for "base"). Subsequent runs are faster.

---

## Command Line Options

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

## Requirements

- **Python 3.10+**
- **FFmpeg** (for audio/video processing)
- **Anthropic API key** ([get one here](https://console.anthropic.com/))

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed installation instructions.

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

---

## How It Works (Technical)

```
+-------------+     +-------------+     +-------------+
|   Video     |---->|   FFmpeg    |---->|   Whisper   |
|   (.mp4)    |     | (audio.wav) |     | (transcript)|
+-------------+     +-------------+     +-------------+
                                               |
                                               v
                                        +-------------+
                                        |  Find words |
                                        | "this/that" |
                                        +-------------+
                                               |
                                               v
+-------------+     +-------------+     +-------------+
| Claude Code |<----| stdout      |<----| Claude API  |
|   (plan)    |     | (notes)     |     |  (analyze)  |
+-------------+     +-------------+     +-------------+
```

1. **FFmpeg** extracts audio from video
2. **Whisper** transcribes with word-level timestamps
3. **Script** finds "pointing words" and extracts frames at those moments
4. **Claude API** analyzes frames + transcript --> structured issue list
5. **Output** goes to stdout and NOTES.md file

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **FFmpeg not found** | Install via `winget install ffmpeg` (Windows) or `brew install ffmpeg` (Mac) |
| **Whisper slow on first run** | Normal - downloads model (~140MB). Subsequent runs are faster |
| **No MP4 files found** | Check `--watch-dir` path is correct and contains `.mp4` files |
| **API key not working** | Verify at console.anthropic.com, check for extra whitespace |
| **Out of memory** | Force CPU mode: `export CUDA_VISIBLE_DEVICES=""` |

---

## Privacy & Security

- **Whisper runs locally** - your audio never leaves your machine
- **Only frames + transcript** go to Claude API
- **No data stored** by the script beyond your output folder
- **API key** stored locally in env var or `~/.anthropic_api_key`

---

## Support & Community

- **Bug Reports**: Use [Issues](../../issues) to report problems
- **Feature Requests**: Submit via [Issues](../../issues)
- **Professional Support**: [Analytic Endeavors](https://www.analyticendeavors.com)
- **Direct Contact**: support@analyticendeavors.com

---

## About Analytic Endeavors

**Claude Quick Video Notes** is developed by [Analytic Endeavors](https://www.analyticendeavors.com), a consulting firm specializing in business intelligence and AI-enhanced productivity tools.

**Founded by Reid Havens & Steve Campbell**, we create professional tools and provide expert consulting services for organizations looking to leverage AI and automation.

### Connect With Us

- **Website**: [analyticendeavors.com](https://www.analyticendeavors.com)
- **LinkedIn**: [Analytic Endeavors](https://linkedin.com/company/analytic-endeavors)
- **Reid Havens**: [LinkedIn](https://linkedin.com/in/reid-havens)

---

## License

MIT License - Do whatever you want with this.

---

**Made with AI by [Reid Havens](https://linkedin.com/in/reid-havens) for anyone who talks while pointing at screens**

*Turn rambling screen recordings into actionable task lists*
