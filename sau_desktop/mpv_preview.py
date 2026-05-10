"""Local video preview widgets for the desktop client."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QLabel, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget


LIBMPV_INSTALL_URL_CN = "https://sourceforge.net/projects/mpv-player-windows/files/libmpv/"


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
                f"国内可访问下载地址：{LIBMPV_INSTALL_URL_CN}\n"
                f"{exc}"
            )
            return None


class QtMediaPreview(QWidget):
    """PySide6/QtMultimedia based preview used before falling back to libmpv."""

    playback_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = None
        self._audio_output = None
        self._video_widget = None
        self._source_path: str | None = None
        self._load_error = ""
        self._paused = True

        self.placeholder = QLabel("等待视频文件")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setObjectName("PreviewPlaceholder")

        self.stack = QStackedLayout()
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.placeholder)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.stack)

    def is_available(self) -> bool:
        return self._ensure_player()

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
        if self._ensure_player():
            self._player.setSource(QUrl.fromLocalFile(source_path))
            self.stack.setCurrentWidget(self._video_widget)
        else:
            self.stack.setCurrentWidget(self.placeholder)

    def toggle_playback(self) -> None:
        if not self._source_path:
            return
        if not self._ensure_player():
            self.placeholder.setText(self._load_error or "Qt Multimedia 初始化失败")
            self.stack.setCurrentWidget(self.placeholder)
            return
        self.stack.setCurrentWidget(self._video_widget)
        if self._paused:
            self._player.play()
            self._paused = False
        else:
            self._player.pause()
            self._paused = True

    def stop(self) -> None:
        if self._player:
            self._player.stop()
        self._paused = True

    def close(self) -> None:
        self.stop()
        super().close()

    def _ensure_player(self) -> bool:
        if self._player:
            return True
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget

            self._video_widget = QVideoWidget()
            self._video_widget.setMinimumSize(320, 220)
            self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._video_widget.setStyleSheet("background: #000000;")
            self.stack.addWidget(self._video_widget)

            self._audio_output = QAudioOutput()
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._audio_output)
            self._player.setVideoOutput(self._video_widget)
            self._player.errorOccurred.connect(self._on_player_error)
            return True
        except Exception as exc:
            self._load_error = f"Qt Multimedia 初始化失败：{exc}"
            return False

    def _on_player_error(self, _error, error_string: str = "") -> None:
        if error_string:
            self._load_error = error_string
        self.playback_failed.emit(self._load_error or "Qt Multimedia 播放失败")


class LocalVideoPreview(QWidget):
    """Prefer bundled Qt playback and fall back to libmpv when needed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.qt_preview = QtMediaPreview(self)
        self.mpv_preview = MpvPreview(self)
        self.qt_preview.playback_failed.connect(self._fallback_to_mpv)
        self._active_preview = self.qt_preview if self.qt_preview.is_available() else self.mpv_preview
        self._source_path: Path | None = None

        self.stack = QStackedLayout()
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.qt_preview)
        self.stack.addWidget(self.mpv_preview)
        self.stack.setCurrentWidget(self._active_preview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.stack)

    def set_placeholder(self, text: str) -> None:
        self._source_path = None
        for preview in (self.qt_preview, self.mpv_preview):
            preview.set_placeholder(text)
        self._active_preview = self.qt_preview if self.qt_preview.is_available() else self.mpv_preview
        self.stack.setCurrentWidget(self._active_preview)

    def set_source(self, file_path: Path) -> None:
        self._source_path = file_path
        self._active_preview = self.qt_preview if self.qt_preview.is_available() else self.mpv_preview
        self._active_preview.set_source(file_path)
        self.stack.setCurrentWidget(self._active_preview)

    def toggle_playback(self) -> None:
        if not self._source_path:
            return
        self._active_preview.toggle_playback()

    def stop(self) -> None:
        for preview in (self.qt_preview, self.mpv_preview):
            preview.stop()

    def close(self) -> None:
        self.stop()
        for preview in (self.qt_preview, self.mpv_preview):
            preview.close()
        super().close()

    def _fallback_to_mpv(self, _reason: str = "") -> None:
        if self._active_preview is not self.qt_preview or not self._source_path:
            return
        self.qt_preview.stop()
        self._active_preview = self.mpv_preview
        self.mpv_preview.set_source(self._source_path)
        self.stack.setCurrentWidget(self.mpv_preview)
        self.mpv_preview.toggle_playback()
