"""Phase 1 UI: import, playback, set start/end, trim & export (background thread)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from app.utils.timecode import format_timecode
from app.video import ffmpeg as ff

DARK_QSS = """
QWidget { background:#15171c; color:#e6e8ee; font-family:'Segoe UI',sans-serif; font-size:13px; }
QPushButton { background:#262a33; border:1px solid #333846; border-radius:8px; padding:8px 14px; }
QPushButton:hover { background:#30353f; }
QPushButton:disabled { color:#666b78; }
QPushButton#primary { background:#6c5ce7; border:none; font-weight:600; }
QPushButton#primary:hover { background:#7d6ff0; }
QProgressBar { border:none; background:#262a33; border-radius:5px; max-height:10px; }
QProgressBar::chunk { background:#6c5ce7; border-radius:5px; }
QSlider::groove:horizontal { height:6px; background:#262a33; border-radius:3px; }
QSlider::handle:horizontal { background:#6c5ce7; width:14px; margin:-5px 0; border-radius:7px; }
QLabel#subtitle { color:#8b90a0; }
"""


class ExportWorker(QObject):
    progress = Signal(float)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, cmd: list[str], total: float) -> None:
        super().__init__()
        self.cmd, self.total, self._cancel = cmd, total, False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            ff.run_with_progress(self.cmd, self.total, self.progress.emit, lambda: self._cancel)
            self.finished.emit(self.cmd[-1])
        except Exception as e:  # always surfaced to the user
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Reel Repurposer")
        self.resize(1100, 720)
        self.setAcceptDrops(True)
        self.info: ff.VideoInfo | None = None
        self.start_s = 0.0
        self.end_s = 0.0
        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None

        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(QAudioOutput(self))
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))

        title = QLabel("🎬 Reel Repurposer")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        sub = QLabel("Turn one long video into dozens of short-video ideas.")
        sub.setObjectName("subtitle")
        self.drop = QLabel("🎥 Drop your long video here")
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setStyleSheet("border:2px dashed #3a4050;border-radius:14px;font-size:16px;padding:18px;")
        browse = QPushButton("Browse Files")
        browse.clicked.connect(self.browse)
        self.meta = QLabel("")
        self.meta.setObjectName("subtitle")

        self.seek = QSlider(Qt.Horizontal)
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.time_lbl = QLabel("00:00:00")
        self.range_lbl = QLabel("Clip: —")

        self.btn_play = QPushButton("Play / Pause (Space)")
        self.btn_play.clicked.connect(self.toggle_play)
        b_back = QPushButton("◀ Frame"); b_back.clicked.connect(lambda: self.step_frame(-1))
        b_fwd = QPushButton("Frame ▶"); b_fwd.clicked.connect(lambda: self.step_frame(1))
        b_in = QPushButton("Set Start (I)"); b_in.clicked.connect(self.set_start)
        b_out = QPushButton("Set End (O)"); b_out.clicked.connect(self.set_end)
        self.btn_export = QPushButton("Export Clip (Ctrl+E)")
        self.btn_export.setObjectName("primary")
        self.btn_export.clicked.connect(self.export_clip)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_export)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0)
        self.status = QLabel("Processing locally"); self.status.setObjectName("subtitle")

        controls = QHBoxLayout()
        for w in (self.btn_play, b_back, b_fwd, b_in, b_out, self.btn_export, self.btn_cancel):
            controls.addWidget(w)
        lay = QVBoxLayout()
        lay.addWidget(title); lay.addWidget(sub); lay.addWidget(self.drop)
        lay.addWidget(browse); lay.addWidget(self.meta)
        lay.addWidget(self.video, 1)
        row = QHBoxLayout(); row.addWidget(self.seek, 1); row.addWidget(self.time_lbl)
        lay.addLayout(row); lay.addWidget(self.range_lbl); lay.addLayout(controls)
        lay.addWidget(self.bar); lay.addWidget(self.status)
        root = QWidget(); root.setLayout(lay); self.setCentralWidget(root)

        for key, fn in (("Space", self.toggle_play), ("Left", lambda: self.nudge(-5)),
                        ("Right", lambda: self.nudge(5)), ("I", self.set_start),
                        ("O", self.set_end), ("Ctrl+E", self.export_clip)):
            QShortcut(QKeySequence(key), self, activated=fn)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        urls = e.mimeData().urls()
        if urls:
            self.load(urls[0].toLocalFile())

    def browse(self) -> None:
        exts = " ".join(f"*{x}" for x in sorted(ff.SUPPORTED_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "Open video", "", f"Video ({exts})")
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        try:
            self.info = ff.probe(path)
        except ff.FFmpegError as e:
            QMessageBox.warning(self, "Cannot open video", str(e)); return
        i = self.info
        self.meta.setText(
            f"{Path(path).name}  •  {format_timecode(i.duration)}  •  {i.width}×{i.height}  •  "
            f"{i.fps:.2f} FPS  •  {i.size_bytes/1e6:.1f} MB  •  Audio: {'Available' if i.has_audio else 'None'}")
        self.player.setSource(QUrl.fromLocalFile(path))
        self.start_s, self.end_s = 0.0, min(i.duration, 60.0)
        self._update_range()

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def nudge(self, secs: float) -> None:
        self.player.setPosition(max(0, self.player.position() + int(secs * 1000)))

    def step_frame(self, n: int) -> None:
        fps = self.info.fps if self.info and self.info.fps > 0 else 30
        self.player.pause(); self.nudge(n / fps)

    def _on_position(self, ms: int) -> None:
        self.seek.setValue(ms); self.time_lbl.setText(format_timecode(ms / 1000))

    def set_start(self) -> None:
        self.start_s = self.player.position() / 1000; self._update_range()

    def set_end(self) -> None:
        self.end_s = self.player.position() / 1000; self._update_range()

    def _update_range(self) -> None:
        self.range_lbl.setText(
            f"Clip: {format_timecode(self.start_s)} → {format_timecode(self.end_s)}  "
            f"({max(0, self.end_s - self.start_s):.1f} s)")

    def export_clip(self) -> None:
        if not self.info:
            QMessageBox.information(self, "Export", "Import a video first."); return
        if self.end_s <= self.start_s:
            QMessageBox.warning(self, "Export", "End must be after start."); return
        dst, _ = QFileDialog.getSaveFileName(self, "Export clip", "clip.mp4", "MP4 (*.mp4)")
        if not dst:
            return
        try:
            ff.check_output_dir(str(Path(dst).parent))
            cmd = ff.build_trim_command(ff.find_binary("ffmpeg"), self.info.path, dst,
                                        self.start_s, self.end_s, has_audio=self.info.has_audio)
        except (ff.FFmpegError, ValueError) as e:
            QMessageBox.critical(self, "Export", str(e)); return
        self._worker = ExportWorker(cmd, self.end_s - self.start_s)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(lambda p: self.bar.setValue(int(p * 100)))
        self._worker.finished.connect(self._done)
        self._worker.failed.connect(self._fail)
        self.btn_export.setEnabled(False); self.btn_cancel.setEnabled(True)
        self.status.setText("Exporting… (processing locally)")
        self._thread.start()

    def _cancel_export(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _finish_thread(self) -> None:
        if self._thread:
            self._thread.quit(); self._thread.wait()
        self.btn_export.setEnabled(True); self.btn_cancel.setEnabled(False)

    def _done(self, path: str) -> None:
        self._finish_thread(); self.status.setText(f"Exported: {path}")

    def _fail(self, msg: str) -> None:
        self._finish_thread(); self.bar.setValue(0); self.status.setText("Export stopped")
        if msg != "Cancelled":
            QMessageBox.critical(self, "Export failed", msg)
