"""mpv/libmpv based video preview widget for the desktop client."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget


def _add_mpv_dll_directories() -> None:
    if not hasattr(os, "add_dll_directory"):
        return
        root = Path(__file__).resolve().parents[1]
    for candidate in (
        root / "runtime" / "mpv",
        root / "vendor" / "mpv",
        root / "mpv",
    ):
        if candidate.exists():
            os.add_dll_directory(str(candidate))


class MpvPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mpv = None
        self._source_path: str | None = None
        self._load_error = ""
        self._paused = True

        self.surface = QWidget()
        self.surface.setAttribute(Qt.WA_NativeWindow, True)
        self.surface.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.surface.setMinimumSize(320, 220)
        self.surface.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.surface.setStyleSheet("background: #000000;")

        self.placeholder = QLabel("等待视频文件")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setObjectName("PreviewPlaceholder")

        self.stack = QStackedLayout()
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.surface)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.stack)

    def set_placeholder(self, text: str) -> None:
        self.stop()
        self._source_path = None
        self.placeholder.setText(text)
        self.stack.setCurrentWidget(self.placeholder)

    def set_source(self, file_path: Path) -> None:
        source_path = str(file_path)
        if self._source_path == source_path:
            return
        self.stop()
        self._source_path = source_path
        self.placeholder.setText(file_path.name)
        self.stack.setCurrentWidget(self.surface)

    def toggle_playback(self) -> None:
        if not self._source_path:
            return
        player = self._ensure_player()
        if not player:
            self.placeholder.setText(self._load_error or "mpv 初始化失败")
            self.stack.setCurrentWidget(self.placeholder)
            return
        self.stack.setCurrentWidget(self.surface)
        if self._paused:
            player.play(self._source_path)
            player.pause = False
            self._paused = False
        else:
            player.pause = True
            self._paused = True

    def stop(self) -> None:
        if self._mpv:
            try:
                self._mpv.command("stop")
            except Exception:
                pass
        self._paused = True

    def close(self) -> None:
        self.stop()
        if self._mpv:
            try:
                self._mpv.terminate()
            except Exception:
                pass
            self._mpv = None
        super().close()

    def _ensure_player(self):
        if self._mpv:
            return self._mpv
        try:
            _add_mpv_dll_directories()
            import mpv

            self._mpv = mpv.MPV(
                wid=str(int(self.surface.winId())),
                input_default_bindings=True,
                input_vo_keyboard=True,
                osc=True,
                keep_open=True,
            )
            return self._mpv
        except Exception as exc:
            self._load_error = (
                "未检测到可用的 libmpv。请安装 mpv/libmpv 运行时，"
                "或运行：python tools/install_mpv_runtime.py\n"
                f"{exc}"
            )
            return None
