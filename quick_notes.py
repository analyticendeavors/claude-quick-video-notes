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
    "this", "that", "here", "there", "these", "those",
    "look", "see", "notice", "button", "color", "element",
    "right here", "over here", "this one", "that one"
]


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
                    "context": context.strip()
                })
                break

    # Deduplicate moments within 2 seconds
    if not moments:
        return []

    deduped = [moments[0]]
    for m in moments[1:]:
        if m["timestamp"] - deduped[-1]["timestamp"] > 2.0:
            deduped.append(m)

    return deduped


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

You just saw {len(frames)} screenshots from a screen recording where the user pointed at UI elements while talking.

Create a structured task list. For each issue:
1. What UI element they pointed at (be specific: button name, location, color)
2. What change they want
3. Any specific values mentioned (colors, sizes, etc.)

Format as markdown:

## Issues Found

### 1. [Short title]
- **Element**: [what they pointed at]
- **Location**: [where on screen]
- **Issue**: [what's wrong]
- **Fix**: [what to do]

(repeat for each issue)

## Summary
[1-2 sentence overview of all changes needed]
"""
    })

    print(f"Calling Claude API with {len(frames)} frames...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
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

    # Find pointing moments
    moments = find_pointing_moments(words_with_times)
    print(f"Found {len(moments)} pointing moments")

    # Fallback: sample evenly if few pointing words detected
    if len(moments) < 3:
        print("Few pointing words detected, sampling frames evenly...")
        num_samples = min(10, max(3, int(duration / 10)))
        moments = [
            {"timestamp": i * duration / num_samples, "context": "[sampled frame]", "word": ""}
            for i in range(num_samples)
        ]

    # Extract frames at pointing moments (max 15)
    frames = []
    for i, moment in enumerate(moments[:15]):
        frame_path = frames_dir / f"frame_{i:02d}_t{moment['timestamp']:.1f}s.jpg"
        if extract_frame_at_time(video_path, moment["timestamp"], frame_path):
            frames.append({
                "path": str(frame_path),
                "timestamp": moment["timestamp"],
                "context": moment["context"]
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
    parser.add_argument(
        "-o", "--output-dir",
        default="./output",
        help="Output directory for notes (default: ./output)"
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
