"""Caption generation: word-timed grouping, SRT for a clip range, and styled ASS."""
from __future__ import annotations
from dataclasses import dataclass
from app.transcription.models import Segment, Word, to_srt

STYLES = {  # name: (font size, bold, outline, primary BGR-hex, highlight)
    "Clean": (56, 0, 2, "FFFFFF", None), "Bold": (78, 1, 5, "FFFFFF", None),
    "Creator": (84, 1, 6, "FFFFFF", "00E5FF"), "Minimal": (40, 0, 1, "F0F0F0", None),
    "Highlight": (66, 1, 4, "FFFFFF", "00D7FF"),
}


@dataclass
class CaptionLine:
    start: float
    end: float
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def clip_words(segs: list[Segment], start: float, end: float) -> list[Word]:
    """Words inside [start,end], shifted so clip starts at 0. Falls back to even timing without word data."""
    out: list[Word] = []
    for s in segs:
        if s.end <= start or s.start >= end: continue
        ws = s.words
        if not ws:
            toks = s.text.split()
            if not toks: continue
            step = (s.end - s.start) / len(toks)
            ws = [Word(t, s.start + i * step, s.start + (i + 1) * step) for i, t in enumerate(toks)]
        out += [Word(w.text, max(0, w.start - start), min(end, w.end) - start) for w in ws if w.start >= start - 0.01 and w.end <= end + 0.01]
    return out


def make_lines(words: list[Word], max_chars: int = 28, max_lines_dur: float = 3.0) -> list[CaptionLine]:
    lines: list[CaptionLine] = []; cur: list[Word] = []
    for w in words:
        trial = " ".join(x.text for x in cur + [w])
        if cur and (len(trial) > max_chars or w.end - cur[0].start > max_lines_dur):
            lines.append(CaptionLine(cur[0].start, cur[-1].end, cur)); cur = []
        cur.append(w)
    if cur: lines.append(CaptionLine(cur[0].start, cur[-1].end, cur))
    return lines


def lines_to_srt(lines: list[CaptionLine]) -> str:
    return to_srt([Segment(l.start, l.end, l.text) for l in lines])


def _ass_t(t: float) -> str:
    cs = int(round(t * 100)); h, r = divmod(cs, 360000); m, r = divmod(r, 6000); s, c = divmod(r, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def to_ass(lines: list[CaptionLine], style: str = "Bold", width: int = 1080, height: int = 1920,
           margin_v: int = 260, font: str = "Arial") -> str:
    size, bold, outline, color, hi = STYLES[style]
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV\n"
            f"Style: Default,{font},{size},&H00{color},&H00000000,&H80000000,{-bold},0,1,{outline},1,2,80,80,{margin_v}\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    ev = []
    for l in lines:
        if hi:  # per-word emphasis: one event per word, active word coloured
            for k, w in enumerate(l.words):
                end = l.words[k + 1].start if k + 1 < len(l.words) else l.end
                txt = " ".join((f"{{\\c&H{hi}&}}{x.text}{{\\c&H{color}&}}" if i == k else x.text) for i, x in enumerate(l.words))
                ev.append(f"Dialogue: 0,{_ass_t(w.start)},{_ass_t(end)},Default,,0,0,0,,{txt}")
        else:
            ev.append(f"Dialogue: 0,{_ass_t(l.start)},{_ass_t(l.end)},Default,,0,0,0,,{l.text}")
    return head + "\n".join(ev) + "\n"
