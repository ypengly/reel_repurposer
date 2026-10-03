"""Local transcription via faster-whisper (optional dependency)."""
from __future__ import annotations
import subprocess, tempfile, os
from typing import Callable
from app.transcription.models import Segment, Word
from app.video.ffmpeg import FFmpegError, find_binary


def extract_audio(video: str, out_wav: str, ffmpeg: str | None = None) -> None:
    ffmpeg = ffmpeg or find_binary("ffmpeg")
    p = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000", out_wav],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise FFmpegError("Could not extract audio (the file may have no audio track):\n" + p.stderr.strip())


def transcribe(video: str, duration: float, model: str = "base", model_path: str | None = None,
               on_progress: Callable[[float], None] = lambda _p: None,
               is_cancelled: Callable[[], bool] = lambda: False) -> list[Segment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Local transcription needs faster-whisper: pip install faster-whisper "
                           "(or import an existing .srt/.vtt transcript instead).") from e
    fd, wav = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    try:
        extract_audio(video, wav)
        wm = WhisperModel(model_path or model, compute_type="int8")  # local, CPU-friendly
        segs_iter, _ = wm.transcribe(wav, word_timestamps=True, vad_filter=True)
        out: list[Segment] = []
        for s in segs_iter:
            if is_cancelled():
                raise RuntimeError("Cancelled")
            out.append(Segment(s.start, s.end, s.text.strip(),
                               [Word(w.word.strip(), w.start, w.end) for w in (s.words or [])]))
            if duration > 0:
                on_progress(min(1.0, s.end / duration))
        return out
    finally:
        if os.path.exists(wav):
            os.remove(wav)
