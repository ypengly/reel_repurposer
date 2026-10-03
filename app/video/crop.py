"""Crop maths, filter graphs and OpenCV face tracking (with center-crop fallback)."""
from __future__ import annotations
from dataclasses import dataclass

OUTPUTS = {"vertical": (1080, 1920), "square": (1080, 1080), "landscape": (1920, 1080)}


def crop_window(src_w: int, src_h: int, out_w: int, out_h: int, cx: float = 0.5) -> tuple[int, int, int, int]:
    """Largest window with the output aspect ratio, horizontally centred at fraction cx, kept inside frame. Even sizes."""
    target = out_w / out_h
    if src_w / src_h > target:
        h = src_h; w = int(round(h * target))
    else:
        w = src_w; h = int(round(w / target))
    w -= w % 2; h -= h % 2
    x = int(round(cx * src_w - w / 2)); x = max(0, min(x, src_w - w)); x -= x % 2
    y = (src_h - h) // 2; y -= y % 2
    return w, h, x, y


def build_vf(mode: str, src_w: int, src_h: int, out: str = "vertical", cx: float = 0.5, subs_path: str | None = None) -> str:
    ow, oh = OUTPUTS[out]
    if mode == "blur":
        vf = (f"split[a][b];[a]scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},boxblur=30:5[bg];"
              f"[b]scale={ow}:{oh}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    else:  # center / manual / smart all reduce to a static crop centred at cx
        w, h, x, y = crop_window(src_w, src_h, ow, oh, 0.5 if mode == "center" else cx)
        vf = f"crop={w}:{h}:{x}:{y},scale={ow}:{oh}"
    if subs_path:
        p = subs_path.replace("\\", "/").replace(":", "\\:")
        vf += f",subtitles='{p}'"
    return vf


def smart_center(video: str, start: float, end: float, samples: int = 12) -> tuple[float, bool]:
    """Median horizontal face position (0..1) over sampled frames. Returns (cx, tracked). Falls back to (0.5, False)."""
    try:
        import cv2, numpy as np
        cap = cv2.VideoCapture(video)
        if not cap.isOpened(): return 0.5, False
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        xs = []
        for i in range(samples):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + (end - start) * (i + 0.5) / samples) * 1000)
            ok, fr = cap.read()
            if not ok: continue
            g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            faces = det.detectMultiScale(g, 1.1, 5, minSize=(60, 60))
            if len(faces):
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                xs.append((x + w / 2) / fr.shape[1])
        cap.release()
        return (float(np.median(xs)), True) if len(xs) >= max(2, samples // 4) else (0.5, False)
    except Exception:
        return 0.5, False
