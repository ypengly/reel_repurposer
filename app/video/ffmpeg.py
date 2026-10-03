"""FFmpeg / ffprobe integration. All heavy work runs in subprocesses."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


class FFmpegError(RuntimeError):
    pass


class FFmpegNotFound(FFmpegError):
    def __init__(self) -> None:
        super().__init__(
            "FFmpeg was not found. Install FFmpeg or configure its location in Settings."
        )


@dataclass(frozen=True)
class VideoInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    size_bytes: int
    has_audio: bool


def find_binary(name: str, configured_dir: Optional[str] = None) -> str:
    if configured_dir:
        for cand in (Path(configured_dir) / name, Path(configured_dir) / f"{name}.exe"):
            if cand.is_file():
                return str(cand)
    found = shutil.which(name)
    if not found:
        raise FFmpegNotFound()
    return found


def _parse_fps(rate: str) -> float:
    try:
        num, den = rate.split("/")
        return float(num) / float(den) if float(den) else 0.0
    except (ValueError, AttributeError):
        try:
            return float(rate)
        except (TypeError, ValueError):
            return 0.0


def parse_probe_json(data: dict, path: str, size_bytes: int) -> VideoInfo:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError("No video stream found in this file.")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise FFmpegError("Could not determine video duration (file may be corrupted).")
    return VideoInfo(
        path=path,
        duration=duration,
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate", "0/1")),
        size_bytes=size_bytes,
        has_audio=has_audio,
    )


def probe(path: str, ffprobe: Optional[str] = None) -> VideoInfo:
    p = Path(path)
    if not p.is_file():
        raise FFmpegError(f"File not found: {path}")
    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise FFmpegError(
            f"Unsupported file type '{p.suffix}'. Supported: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
    exe = ffprobe or find_binary("ffprobe")
    proc = subprocess.run(
        [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe could not read this file (corrupted or unsupported codec):\n{proc.stderr.strip()}")
    return parse_probe_json(json.loads(proc.stdout), str(p), p.stat().st_size)


def build_trim_command(
    ffmpeg: str, src: str, dst: str, start: float, end: float,
    *, crf: int = 20, preset: str = "veryfast", has_audio: bool = True,
    vf: Optional[str] = None, codec: str = "libx264",
) -> list[str]:
    """Frame-accurate trim (re-encode). -ss before -i for fast seeking."""
    if end <= start:
        raise ValueError("End must be after start")
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
           "-ss", f"{start:.3f}", "-i", src, "-t", f"{end - start:.3f}"]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-c:v", codec, "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-b:a", "160k"] if has_audio else ["-an"]
    cmd += ["-movflags", "+faststart", dst]
    return cmd


_TIME_RE = re.compile(r"out_time_(?:us|ms)=(\d+)")


def run_with_progress(
    cmd: list[str], total_seconds: float,
    on_progress: Callable[[float], None] = lambda _p: None,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> None:
    """Run ffmpeg, reporting 0..1 progress parsed from `-progress pipe:1`."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if is_cancelled():
                proc.kill()
                raise FFmpegError("Cancelled")
            m = _TIME_RE.match(line.strip())
            if m and total_seconds > 0:
                on_progress(min(1.0, int(m.group(1)) / 1_000_000 / total_seconds))
        err = proc.stderr.read() if proc.stderr else ""
        if proc.wait() != 0:
            raise FFmpegError(f"Export failed:\n{err.strip()}")
        on_progress(1.0)
    finally:
        if proc.poll() is None:
            proc.kill()


def check_output_dir(path: str, min_free_bytes: int = 200 * 1024 * 1024) -> None:
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise FFmpegError(f"Invalid output directory: {e}") from e
    if not os.access(p, os.W_OK):
        raise FFmpegError(f"Output directory is not writable: {path}")
    if shutil.disk_usage(p).free < min_free_bytes:
        raise FFmpegError("Insufficient disk space in the output directory.")
