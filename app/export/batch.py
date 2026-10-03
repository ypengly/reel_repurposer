"""Export package per clip + batch runner with cancel and retry of failures."""
from __future__ import annotations
import csv, json, os, tempfile
from pathlib import Path
from typing import Callable
from app.captions.captions import clip_words, make_lines, lines_to_srt, to_ass
from app.clip_detection.detector import Clip, make_hooks, make_description
from app.transcription.models import Segment
from app.video import crop, ffmpeg as ff


def export_clip(info: ff.VideoInfo, clip: Clip, segs: list[Segment], out_root: str, index: int, *,
                mode: str = "center", out: str = "vertical", caption_style: str | None = "Bold",
                crf: int = 20, codec: str = "libx264", on_progress: Callable[[float], None] = lambda _p: None,
                is_cancelled: Callable[[], bool] = lambda: False) -> Path:
    d = Path(out_root) / f"Clip_{index:03d}"
    ff.check_output_dir(str(d))
    lines = make_lines(clip_words(segs, clip.start, clip.end))
    ow, oh = crop.OUTPUTS[out]
    ass = None
    if caption_style and lines:
        ass = str(d / "captions.ass"); Path(ass).write_text(to_ass(lines, caption_style, ow, oh), encoding="utf-8")
    cx, _tracked = crop.smart_center(info.path, clip.start, clip.end) if mode == "smart" else (0.5, False)
    vf = crop.build_vf(mode, info.width, info.height, out, cx, ass)
    cmd = ff.build_trim_command(ff.find_binary("ffmpeg"), info.path, str(d / "video.mp4"), clip.start, clip.end,
                                crf=crf, vf=vf, has_audio=info.has_audio, codec=codec)
    ff.run_with_progress(cmd, clip.duration, on_progress, is_cancelled)
    (d / "captions.srt").write_text(lines_to_srt(lines), encoding="utf-8")
    (d / "transcript.txt").write_text(clip.text, encoding="utf-8")
    (d / "title.txt").write_text(clip.title, encoding="utf-8")
    (d / "description.txt").write_text(make_description(clip), encoding="utf-8")
    (d / "hooks.txt").write_text("\n".join(f"{i}. {h}" for i, h in enumerate(make_hooks(clip), 1)), encoding="utf-8")
    clip.exported = True
    return d


def run_batch(info, clips: list[Clip], segs, out_root: str, on_clip: Callable[[int, float], None] = lambda i, p: None,
              is_cancelled: Callable[[], bool] = lambda: False, **kw) -> dict[int, str]:
    """Returns {index: error} for failures so the caller can retry only those."""
    failed: dict[int, str] = {}
    for n, c in enumerate(clips, 1):
        if is_cancelled(): break
        try:
            export_clip(info, c, segs, out_root, n, on_progress=lambda p, n=n: on_clip(n, p), is_cancelled=is_cancelled, **kw)
        except Exception as e:
            failed[n] = str(e)
    return failed


def export_metadata(clips: list[Clip], path: str) -> None:
    rows = [dict(index=i, start=c.start, end=c.end, duration=round(c.duration, 2), score=c.score, title=c.title,
                 hook=c.hook, categories="|".join(c.categories), favorite=c.favorite, exported=c.exported)
            for i, c in enumerate(clips, 1)]
    if path.lower().endswith(".json"):
        Path(path).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["index"]); w.writeheader(); w.writerows(rows)
