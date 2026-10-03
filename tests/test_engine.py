import json, shutil, subprocess
from pathlib import Path
import pytest
from app.transcription.models import Segment, parse_srt, to_srt, to_vtt, search
from app.clip_detection.detector import detect_clips, make_hooks, make_titles
from app.captions.captions import clip_words, make_lines, to_ass
from app.video import crop, ffmpeg as ff
from app.projects.store import save_project, load_project
from app.export import batch


def make_segs():
    txt = ["The biggest mistake I made when starting my business was doing everything myself.",
           "I thought working harder would solve the problem.", "But eventually I realized you need to delegate.",
           "Here's how you can start: first list your tasks, then pick three you can hand off.",
           "That works because your time is your most valuable asset."]
    return [Segment(i * 8.0, i * 8.0 + 7.5, t) for i, t in enumerate(txt * 2)]


def test_srt_roundtrip_and_search():
    segs = make_segs()
    back = parse_srt(to_srt(segs)); assert len(back) == len(segs) and abs(back[1].start - 8.0) < .01
    assert parse_srt(to_vtt(segs))[0].text == segs[0].text
    assert search(segs, "DELEGATE")
    with pytest.raises(ValueError): parse_srt("garbage")


def test_detection_bounds_and_explanations():
    clips = detect_clips(make_segs(), 15, 40)
    assert clips
    for c in clips:
        assert 15 <= c.duration <= 40 and 0 <= c.score <= 100 and c.reasons and c.categories
    assert all(a.end <= b.start for a, b in zip(clips, clips[1:]))
    assert make_hooks(clips[0]) and make_titles(clips[0])


def test_caption_timing_and_ass():
    words = clip_words(make_segs(), 8.0, 30.0)
    assert words[0].start == 0 and all(w.end <= 22.01 for w in words)
    lines = make_lines(words); assert all(len(l.text) <= 40 for l in lines)
    assert "Dialogue:" in to_ass(lines, "Creator")


def test_crop_math():
    w, h, x, y = crop.crop_window(1920, 1080, 1080, 1920, 0.5)
    assert (w, h) == (608, 1080) and x == 656 and y == 0
    assert crop.crop_window(1920, 1080, 1080, 1920, 0.0)[2] == 0
    assert crop.crop_window(1920, 1080, 1080, 1920, 1.0)[2] + 608 <= 1920
    assert "crop=608:1080" in crop.build_vf("center", 1920, 1080)


def test_project_roundtrip(tmp_path):
    clips = detect_clips(make_segs(), 15, 40); clips[0].favorite = True
    p = str(tmp_path / "p.rrp"); save_project(p, "v.mp4", make_segs(), clips, {"a": 1})
    v, s, c, st = load_project(p)
    assert v == "v.mp4" and len(s) == 10 and c[0].favorite and st == {"a": 1}
    (tmp_path / "bad").write_text("x")
    with pytest.raises(ValueError): load_project(str(tmp_path / "bad"))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no ffmpeg")
def test_full_export_package(tmp_path):
    src = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=d=45:s=640x360:r=24", "-f", "lavfi", "-i", "sine=d=45",
                    "-shortest", str(src)], check=True, capture_output=True)
    info = ff.probe(str(src)); segs = make_segs()
    clip = detect_clips(segs, 15, 40)[0]
    failed = batch.run_batch(info, [clip], segs, str(tmp_path / "out"), mode="center", caption_style="Bold")
    assert not failed, failed
    d = tmp_path / "out" / "Clip_001"
    for f in ("video.mp4", "captions.srt", "transcript.txt", "title.txt", "description.txt", "hooks.txt"):
        assert (d / f).exists()
    o = ff.probe(str(d / "video.mp4")); assert (o.width, o.height) == (1080, 1920)
    batch.export_metadata([clip], str(tmp_path / "m.json")); assert json.loads((tmp_path / "m.json").read_text())
