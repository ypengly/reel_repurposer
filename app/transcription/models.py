"""Transcript data model + TXT/SRT/VTT import/export."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from app.utils.timecode import format_timecode


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


def _ts(sec: float, sep: str) -> str:
    return format_timecode(sec, with_ms=True).replace(".", sep)


def to_srt(segs: list[Segment]) -> str:
    return "".join(f"{i}\n{_ts(s.start, ',')} --> {_ts(s.end, ',')}\n{s.text.strip()}\n\n"
                   for i, s in enumerate(segs, 1))


def to_vtt(segs: list[Segment]) -> str:
    return "WEBVTT\n\n" + "".join(f"{_ts(s.start, '.')} --> {_ts(s.end, '.')}\n{s.text.strip()}\n\n" for s in segs)


def to_txt(segs: list[Segment]) -> str:
    return "\n".join(f"[{format_timecode(s.start)}] {s.text.strip()}" for s in segs)


_TS = r"(\d+):(\d{2}):(\d{2})[,.](\d{3})"
_CUE = re.compile(_TS + r"\s*-->\s*" + _TS)


def _sec(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(text: str) -> list[Segment]:
    """Parses SRT or VTT. Raises ValueError if no cues are found."""
    out: list[Segment] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        for i, ln in enumerate(lines):
            m = _CUE.search(ln)
            if m:
                g = m.groups()
                body = " ".join(x.strip() for x in lines[i + 1:] if x.strip())
                if body:
                    out.append(Segment(_sec(*g[:4]), _sec(*g[4:]), body))
                break
    if not out:
        raise ValueError("No subtitle cues found.")
    return out


def search(segs: list[Segment], query: str) -> list[int]:
    q = query.lower().strip()
    return [i for i, s in enumerate(segs) if q and q in s.text.lower()]
