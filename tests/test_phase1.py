import shutil
import subprocess

import pytest

from app.utils.timecode import clamp_range, format_timecode, parse_timecode
from app.video import ffmpeg as ff


def test_format_and_parse_roundtrip():
    assert format_timecode(5072) == "01:24:32"
    assert parse_timecode("01:24:32") == 5072
    assert parse_timecode("12:42") == 762
    assert format_timecode(1.5, with_ms=True) == "00:00:01.500"


def test_invalid_timecode():
    for bad in ("", "a:b", "1:2:3:4", "-5"):
        with pytest.raises(ValueError):
            parse_timecode(bad)


def test_clamp_range():
    assert clamp_range(-5, 500, 100) == (0.0, 100.0)
    with pytest.raises(ValueError):
        clamp_range(50, 50, 100)


def test_parse_probe_json():
    data = {"format": {"duration": "5072.5"},
            "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001"},
                        {"codec_type": "audio"}]}
    info = ff.parse_probe_json(data, "x.mp4", 10)
    assert (info.width, info.height, info.has_audio) == (1920, 1080, True)
    assert abs(info.fps - 29.97) < 0.01


def test_probe_no_video_stream():
    with pytest.raises(ff.FFmpegError):
        ff.parse_probe_json({"format": {"duration": "1"}, "streams": [{"codec_type": "audio"}]}, "x", 1)


def test_probe_rejects_bad_extension(tmp_path):
    f = tmp_path / "a.txt"; f.write_text("x")
    with pytest.raises(ff.FFmpegError):
        ff.probe(str(f))


def test_trim_command_validation():
    with pytest.raises(ValueError):
        ff.build_trim_command("ffmpeg", "a", "b", 10, 5)
    cmd = ff.build_trim_command("ffmpeg", "a.mp4", "b.mp4", 10, 40, has_audio=False)
    assert "-an" in cmd and cmd[cmd.index("-t") + 1] == "30.000"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_real_export(tmp_path):
    src, dst = tmp_path / "in.mp4", tmp_path / "out.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=d=6:s=320x240:r=24",
                    "-f", "lavfi", "-i", "sine=d=6", "-shortest", str(src)],
                   check=True, capture_output=True)
    info = ff.probe(str(src))
    assert info.has_audio and 5.5 < info.duration < 6.5
    seen = []
    cmd = ff.build_trim_command("ffmpeg", str(src), str(dst), 1, 4)
    ff.run_with_progress(cmd, 3, seen.append)
    assert seen and seen[-1] == 1.0
    assert 2.5 < ff.probe(str(dst)).duration < 3.5
