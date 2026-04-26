"""关于页面."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from sau_desktop._shared import page_header


class AboutPage(QWidget):
    def __init__(self):
        super().__init__()
        text = QLabel("拾光分发 1.0\n本地 PySide6 客户端\nFlask/Vue Web 主路径已废弃。")
        text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(page_header("关于", "本地客户端版本信息"))
        layout.addWidget(text)
        layout.addStretch()
