#!/usr/bin/env python3
"""
Video-to-Action-Plan: Point + Talk → Structured Task List

Record a screen video, point at UI elements while talking about changes,
get a structured action plan.

Workflow:
1. Whisper transcribes with word-level timestamps (local, free)
2. Detects "this/that/here" moments → extracts frames at those times
3. Claude API analyzes frames + transcript → structured issues
4. Outputs to stdout for Claude Code integration
"""
import sys
import os
import json
import subprocess
import shutil
import base64
from pathlib import Path
from datetime import datetime

# Words that indicate pointing - extract frame at these moments
POINTING_WORDS = [
    # Demonstratives
    "this", "that", "here", "there", "these", "those",
    "right here", "over here", "this one", "that one",
    # Attention words
    "look", "see", "notice", "check", "watch",
    # UI elements
    "button", "color", "element", "icon", "label", "text", "header",
    "section", "panel", "tab", "menu", "dropdown", "field", "input",
    # Action words (indicates something needs to change)
    "change", "fix", "update", "move", "add", "remove", "delete",
    "adjust", "modify", "replace", "swap", "resize", "align",
    # Problem indicators
    "wrong", "issue", "problem", "bug", "broken", "needs", "should",
    "doesn't", "isn't", "weird", "off", "bad", "ugly", "confusing"
]

# Frame extraction settings - scale with video duration
MIN_FRAMES = 5            # Minimum frames to extract
MAX_FRAMES_SHORT = 25     # Max frames for videos under 60s
MAX_FRAMES_MEDIUM = 40    # Max frames for videos 60-180s
MAX_FRAMES_LONG = 60      # Max frames for videos over 180s
CONTINUOUS_INTERVAL = 4   # Also sample every N seconds to ensure coverage
DEDUP_THRESHOLD = 1.5     # Deduplicate frames within this window (seconds)


def find_ffmpeg_windows() -> str | None:
    """Try to find FFmpeg in common Windows installation locations."""
    if sys.platform != "win32":
        return None

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        return None

    # Check WinGet packages folder for FFmpeg
    winget_packages = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
    if winget_packages.exists():
        for ffmpeg_dir in winget_packages.glob("*FFmpeg*/**/bin"):
            ffmpeg_exe = ffmpeg_dir / "ffmpeg.exe"
            if ffmpeg_exe.exists():
                return str(ffmpeg_dir)

    # Check common installation paths
    common_paths = [
        Path(local_appdata) / "Programs" / "ffmpeg" / "bin",
        Path("C:/ffmpeg/bin"),
        Path("C:/Program Files/ffmpeg/bin"),
    ]
    for path in common_paths:
        if (path / "ffmpeg.exe").exists():
            return str(path)

    return None


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available in PATH or common locations."""
    if shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None:
        return True

    # Try to find FFmpeg in common Windows locations
    ffmpeg_path = find_ffmpeg_windows()
    if ffmpeg_path:
        # Add to PATH for this session
        os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ.get("PATH", "")
        return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

    return False


def get_latest_mp4(folder: str) -> Path:
    """Get most recent MP4 from folder."""
    folder_path = Path(folder)
    if not folder_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    mp4_files = list(folder_path.glob("*.mp4"))
    if not mp4_files:
        raise FileNotFoundError(f"No MP4 files in {folder}")
    return max(mp4_files, key=lambda p: p.stat().st_mtime)


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds."""
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def extract_audio(video_path: Path, output_path: Path) -> bool:
    """Extract audio from video as WAV."""
    cmd = ["ffmpeg", "-y", "-i", str(video_path),
           "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
           str(output_path)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def transcribe_with_timestamps(audio_path: Path) -> tuple[str, list]:
    """Transcribe audio with word-level timestamps using Whisper.

    Returns:
        tuple: (full_text, list of {word, start, end} dicts)
    """
    import whisper
    model = whisper.load_model("base")
    result = model.transcribe(str(audio_path), language="en", word_timestamps=True)

    words_with_times = []
    for segment in result.get("segments", []):
        for word_info in segment.get("words", []):
            words_with_times.append({
                "word": word_info.get("word", "").strip(),
                "start": word_info.get("start", 0),
                "end": word_info.get("end", 0)
            })

    return result["text"], words_with_times


def find_pointing_moments(words_with_times: list) -> list:
    """Find timestamps where user is pointing at something."""
    moments = []
    text_so_far = ""

    for i, word_info in enumerate(words_with_times):
        word = word_info["word"].lower().strip(".,!?")
        text_so_far += " " + word

        for pointer in POINTING_WORDS:
            if pointer in word or pointer in text_so_far[-50:].lower():
                start_idx = max(0, i - 3)
                end_idx = min(len(words_with_times), i + 4)
                context = " ".join(w["word"] for w in words_with_times[start_idx:end_idx])

                moments.append({
                    "timestamp": word_info["start"],
                    "word": word,
                    "context": context.strip(),
                    "source": "keyword"
                })
                break

    # Deduplicate moments within threshold
    if not moments:
        return []

    deduped = [moments[0]]
    for m in moments[1:]:
        if m["timestamp"] - deduped[-1]["timestamp"] > DEDUP_THRESHOLD:
            deduped.append(m)

    return deduped


def get_max_frames(duration: float) -> int:
    """Get maximum frames based on video duration."""
    if duration < 60:
        return MAX_FRAMES_SHORT
    elif duration < 180:
        return MAX_FRAMES_MEDIUM
    else:
        return MAX_FRAMES_LONG


def generate_continuous_samples(duration: float, existing_moments: list) -> list:
    """Generate continuous frame samples to ensure nothing is missed.

    Fills gaps between pointing moments and ensures regular coverage.
    """
    samples = []
    existing_times = {m["timestamp"] for m in existing_moments}

    # Sample every CONTINUOUS_INTERVAL seconds
    current_time = 0.5  # Start slightly into the video
    while current_time < duration - 0.5:
        # Check if we already have a frame near this time
        has_nearby = any(abs(t - current_time) < DEDUP_THRESHOLD for t in existing_times)
        if not has_nearby:
            samples.append({
                "timestamp": current_time,
                "word": "",
                "context": "[continuous sample]",
                "source": "continuous"
            })
        current_time += CONTINUOUS_INTERVAL

    return samples


def extract_frame_at_time(video_path: Path, timestamp: float, output_path: Path) -> bool:
    """Extract a single frame at specific timestamp."""
    cmd = ["ffmpeg", "-y", "-ss", str(timestamp),
           "-i", str(video_path), "-frames:v", "1", "-q:v", "2",
           str(output_path)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def image_to_base64(path: str) -> str:
    """Convert image file to base64 string."""
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_api_key() -> str:
    """Get Anthropic API key from environment or file."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    key_file = Path.home() / ".anthropic_api_key"
    if key_file.exists():
        return key_file.read_text().strip()

    return ""


def analyze_with_claude(transcript: str, frames: list, video_name: str) -> str:
    """Send frames + transcript to Claude API for analysis."""
    import anthropic

    api_key = get_api_key()
    if not api_key:
        return "[ERROR: Set ANTHROPIC_API_KEY env var or create ~/.anthropic_api_key file]"

    client = anthropic.Anthropic(api_key=api_key)

    content = []

    for frame in frames:
        try:
            img_data = image_to_base64(frame["path"])
            content.append({
                "type": "text",
                "text": f"[Frame at {frame['timestamp']:.1f}s - User said: \"{frame['context']}\"]"
            })
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img_data}
            })
        except Exception as e:
            print(f"Warning: Could not load {frame['path']}: {e}")

    content.append({
        "type": "text",
        "text": f"""
FULL TRANSCRIPT:
{transcript}

---

You just saw {len(frames)} screenshots from a screen recording where the user pointed at UI elements while talking about changes they want.

Create a structured task list. For each issue:
1. What UI element they pointed at (be specific: button name, location, color, text)
2. What change they want
3. Any specific values mentioned (colors, sizes, spacing, etc.)

Format as markdown:

## Issues Found

### 1. [Short title]
- **Element**: [what they pointed at - be specific]
- **Location**: [where on screen - top/bottom, left/right, which section/panel]
- **Current State**: [what it looks like now]
- **Requested Change**: [what they want it to become]
- **Specific Values**: [any colors, sizes, spacing mentioned, or "None specified"]

(repeat for each issue)

## Clarifying Questions

If anything is unclear or ambiguous, list specific questions here. For example:
- "You mentioned 'make this bigger' but didn't specify a size - what dimensions?"
- "The button color change - did you mean the background or the text?"
- "Should this change apply everywhere or just this specific instance?"

If everything is clear, write "None - all requirements are clear."

## Complexity Assessment

Rate the overall task complexity and recommend an approach:
- **Simple** (1-3 quick fixes): Proceed directly with implementation
- **Medium** (4-8 changes, single file/area): Brief planning, then implement
- **Complex** (9+ changes, multiple files, architectural): **Recommend Plan Mode** - create implementation plan before coding

**Recommendation**: [Simple/Medium/Complex] - [Brief rationale]

## Chat Plans

Break all issues into logical groups that can each be handled by a separate Claude Code session. This prevents context loss from overloading a single chat.

**Grouping rules:**
- Group by area/section/component of the UI or codebase
- Keep tightly related changes together (dependencies, shared files)
- Each group should be independently actionable
- Aim for 3-6 issues per group maximum
- Simple tasks (1-3 total issues) = 1 chat, no splitting needed

For EACH chat group, produce a self-contained block formatted exactly like this:

### Chat [N]: [Descriptive Group Name]
**Focus area**: [which section/component/files this covers]
**Issues**: #[list the issue numbers from above]
**Dependencies**: [any other chat groups that should be completed first, or "None"]

**Prompt to paste into Claude Code:**
```
I need to make the following changes to [project/area]. Here is the context from a video review:

[For each issue in this group, restate it concisely with all specific details - element, location, current state, requested change, and any specific values. Do NOT just reference issue numbers - the other Claude session has no context about those numbers. Include full details.]

Please implement these changes. After completing each one, briefly confirm what was done.
```

(Repeat for each chat group)

### Execution Order
List the recommended order to run the chats, noting which can run in parallel vs which depend on earlier chats completing first.

## Summary
[2-3 sentence overview of all changes needed and suggested implementation order]
"""
    })

    print(f"Calling Claude API with {len(frames)} frames...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": content}]
    )

    return response.content[0].text


def process_video(video_path: Path, output_dir: Path) -> dict:
    """Process video and generate notes.

    Args:
        video_path: Path to the video file
        output_dir: Directory to save output files

    Returns:
        dict with processing results
    """
    print(f"Processing: {video_path.name}")

    # Create output directories
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"{video_path.stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = run_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    duration = get_video_duration(video_path)
    print(f"Duration: {duration:.1f}s")

    # Extract and transcribe audio
    print("Transcribing with Whisper...")
    audio_path = run_dir / "audio.wav"
    transcript = ""
    words_with_times = []

    if extract_audio(video_path, audio_path):
        transcript, words_with_times = transcribe_with_timestamps(audio_path)
        audio_path.unlink(missing_ok=True)  # Clean up audio file

    print(f"Transcript: {len(transcript)} chars, {len(words_with_times)} words")

    # Find pointing moments from keywords
    keyword_moments = find_pointing_moments(words_with_times)
    print(f"Found {len(keyword_moments)} keyword-triggered moments")

    # Generate continuous samples to fill gaps and ensure coverage
    continuous_samples = generate_continuous_samples(duration, keyword_moments)
    print(f"Generated {len(continuous_samples)} continuous samples")

    # Combine and sort all moments by timestamp
    all_moments = keyword_moments + continuous_samples
    all_moments.sort(key=lambda m: m["timestamp"])

    # Determine max frames based on duration
    max_frames = get_max_frames(duration)
    print(f"Max frames for {duration:.0f}s video: {max_frames}")

    # If we have too many moments, prioritize keyword moments
    if len(all_moments) > max_frames:
        # Keep all keyword moments, then fill with continuous samples
        keyword_count = len(keyword_moments)
        if keyword_count >= max_frames:
            # Too many keywords - just use keyword moments evenly distributed
            all_moments = sorted(keyword_moments, key=lambda m: m["timestamp"])[:max_frames]
        else:
            # Use all keywords + some continuous samples
            remaining_slots = max_frames - keyword_count
            continuous_samples = continuous_samples[:remaining_slots]
            all_moments = keyword_moments + continuous_samples
            all_moments.sort(key=lambda m: m["timestamp"])

    # Extract frames
    frames = []
    for i, moment in enumerate(all_moments[:max_frames]):
        source_tag = moment.get("source", "keyword")[:1].upper()  # K or C
        frame_path = frames_dir / f"frame_{i:02d}_{source_tag}_t{moment['timestamp']:.1f}s.jpg"
        if extract_frame_at_time(video_path, moment["timestamp"], frame_path):
            frames.append({
                "path": str(frame_path),
                "timestamp": moment["timestamp"],
                "context": moment["context"],
                "source": moment.get("source", "keyword")
            })

    print(f"Extracted {len(frames)} frames")

    # Analyze with Claude API
    analysis = analyze_with_claude(transcript, frames, video_path.name)

    # Build result
    result = {
        "video_name": video_path.name,
        "video_path": str(video_path),
        "duration_seconds": duration,
        "transcript": transcript,
        "analysis": analysis,
        "frames_analyzed": len(frames),
        "output_dir": str(run_dir),
        "processed_at": datetime.now().isoformat()
    }

    # Save JSON
    (run_dir / "notes.json").write_text(json.dumps(result, indent=2))

    # Save readable NOTES.md
    notes_md = f"""# Video Notes: {video_path.name}

**Duration:** {duration:.1f}s | **Frames Analyzed:** {len(frames)} | **Processed:** {result['processed_at']}

---

{analysis}

---

## Raw Transcript

{transcript}
"""
    (run_dir / "NOTES.md").write_text(notes_md)

    print(f"\n[OK] Notes saved to: {run_dir / 'NOTES.md'}")

    # Output to stdout for Claude Code integration
    print("\n" + "="*60)
    print("NOTES CONTENT:")
    print("="*60)
    print(notes_md)
    print("="*60)

    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Video-to-Action-Plan: Record screen video → get structured task list",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s video.mp4                    Process a specific video
  %(prog)s --watch-dir ~/Videos         Process latest video from folder
  %(prog)s video.mp4 -o ./notes         Save output to ./notes folder

Requirements:
  - FFmpeg (install via: winget install ffmpeg / brew install ffmpeg)
  - Python packages: pip install openai-whisper anthropic
  - API key: Set ANTHROPIC_API_KEY env var or create ~/.anthropic_api_key
"""
    )
    parser.add_argument(
        "video",
        nargs="?",
        help="Path to video file (optional if --watch-dir is set)"
    )
    parser.add_argument(
        "-w", "--watch-dir",
        help="Folder to find latest MP4 from (used if no video specified)"
    )
    # Default output to script's directory, not current working directory
    script_dir = Path(__file__).parent
    parser.add_argument(
        "-o", "--output-dir",
        default=str(script_dir / "output"),
        help="Output directory for notes (default: ./output relative to script)"
    )

    args = parser.parse_args()

    # Check FFmpeg
    if not check_ffmpeg():
        print("ERROR: FFmpeg not found in PATH")
        print("Install: winget install ffmpeg (Windows) or brew install ffmpeg (Mac)")
        if sys.platform == "win32":
            print("If already installed, see README.md 'Windows PATH Issues' section")
        sys.exit(1)

    # Determine video path
    if args.video:
        video_path = Path(args.video)
        if not video_path.exists():
            print(f"ERROR: Video not found: {args.video}")
            sys.exit(1)
    elif args.watch_dir:
        try:
            video_path = get_latest_mp4(args.watch_dir)
            print(f"Found latest video: {video_path}")
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    else:
        print("ERROR: Provide a video path or use --watch-dir")
        parser.print_help()
        sys.exit(1)

    # Process
    output_dir = Path(args.output_dir)
    process_video(video_path, output_dir)


if __name__ == "__main__":
    main()
