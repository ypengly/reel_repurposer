# Reel Repurposer 🎬

Import a long video, play it, mark a start/end, and export the clip locally with FFmpeg. Processing is 100% local.

## Setup
1. Install Python 3.11+ (python.org; tick "Add to PATH").
2. Install FFmpeg (Windows: `winget install Gyan.FFmpeg`; macOS: `brew install ffmpeg`) and make sure `ffmpeg` and `ffprobe` are on PATH.
3. `pip install -r requirements.txt`
4. `python main.py`

## Shortcuts
Space play/pause, ←/→ seek 5 s, I set start, O set end, Ctrl+E export.

## Tests
`python -m pytest`

## Status
Engine (Phases 2-6 logic) done and tested; UI wiring for it is next.
