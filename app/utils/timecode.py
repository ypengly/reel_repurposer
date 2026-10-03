"""Timestamp helpers."""
from __future__ import annotations


def format_timecode(seconds: float, with_ms: bool = False) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    base = f"{h:02d}:{m:02d}:{s:02d}"
    return f"{base}.{ms:03d}" if with_ms else base


def parse_timecode(text: str) -> float:
    """Accepts SS, MM:SS, HH:MM:SS (each optionally with .fraction)."""
    parts = text.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"Invalid timecode: {text!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError as e:
        raise ValueError(f"Invalid timecode: {text!r}") from e
    if any(n < 0 for n in nums):
        raise ValueError(f"Invalid timecode: {text!r}")
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def clamp_range(start: float, end: float, duration: float) -> tuple[float, float]:
    """Clamp a clip range into [0, duration], guaranteeing start < end."""
    start = max(0.0, min(start, duration))
    end = max(0.0, min(end, duration))
    if end <= start:
        raise ValueError("End must be after start")
    return start, end
