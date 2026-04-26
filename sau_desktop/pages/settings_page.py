"""系统设置页面."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sau_core.services import ProcessingService, SettingsService
from sau_desktop._shared import EventBus, make_button, page_header


class SettingsPage(QWidget):
    def __init__(self, settings_service: SettingsService, processing_service: ProcessingService, event_bus: EventBus):
        super().__init__()
        self.settings_service = settings_service
        self.processing_service = processing_service
        self.event_bus = event_bus
        self._dirty = False
        self.proxy = QLineEdit()
        self.cookie_status = QLabel()
        self.auto_process = QCheckBox("下载后自动处理")
        self.trim_head_enabled = QCheckBox("启用片头裁剪")
        self.trim_head_min = self._double_spin(0, 10, 0.1)
        self.trim_head_max = self._double_spin(0, 10, 0.1)
        self.trim_tail_enabled = QCheckBox("启用片尾裁剪")
        self.trim_tail_min = self._double_spin(0, 10, 0.1)
        self.trim_tail_max = self._double_spin(0, 10, 0.1)
        self.speed_enabled = QCheckBox("启用变速")
        self.speed_min = self._double_spin(0.5, 2.0, 0.01)
        self.speed_max = self._double_spin(0.5, 2.0, 0.01)
        self.crop_enabled = QCheckBox("启用裁剪")
        self.crop_min = self._double_spin(0, 10, 0.1)
        self.crop_max = self._double_spin(0, 10, 0.1)
        self.pink_enabled = QCheckBox("启用粉色滤镜")
        self.pink_strength = self._double_spin(0, 1, 0.01)
        self.light_sweep = QCheckBox("启用扫光")
        self.frame_drop_enabled = QCheckBox("启用随机抽帧")
        self.frame_drop_strength = self._double_spin(0, 0.2, 0.01)
        self.edge_guard_enabled = QCheckBox("启用边缘保护")
        self.edge_guard_pixels = QSpinBox()
        self.edge_guard_pixels.setRange(0, 32)
        self.edge_guard_pixels.setFixedWidth(90)
        self.max_concurrent = QSpinBox()
        self.max_concurrent.setRange(1, 8)
        self.max_concurrent.setFixedWidth(90)
        self.hardware = QComboBox()
        self.hardware.addItems(["cpu", "gpu"])
        self.hardware.setFixedWidth(90)

        proxy_form = QFormLayout()
        proxy_form.setLabelAlignment(Qt.AlignRight)
        proxy_form.addRow("下载代理", self.proxy)
        proxy_group = self._settings_group("代理设置", proxy_form)

        cookie_form = QFormLayout()
        cookie_form.setLabelAlignment(Qt.AlignRight)
        cookie_form.addRow("当前 Cookie", self.cookie_status)
        cookie_buttons = QHBoxLayout()
        cookie_buttons.addWidget(make_button("导入 YouTube Cookie", self.import_youtube_cookie))
        cookie_buttons.addWidget(make_button("清除 Cookie", self.clear_youtube_cookie, danger=True))
        cookie_buttons.addStretch()
        cookie_form.addRow("操作", cookie_buttons)
        cookie_group = self._settings_group("YouTube Cookie 设置", cookie_form)

        process_grid = QGridLayout()
        process_grid.setHorizontalSpacing(10)
        process_grid.setVerticalSpacing(6)
        for column, width in ((0, 130), (1, 52), (2, 90), (3, 52), (4, 90)):
            process_grid.setColumnMinimumWidth(column, width)
        process_grid.setColumnStretch(5, 1)
        self._add_setting_row(process_grid, 0, self.trim_head_enabled, [("最小秒", self.trim_head_min), ("最大秒", self.trim_head_max)])
        self._add_setting_row(process_grid, 1, self.trim_tail_enabled, [("最小秒", self.trim_tail_min), ("最大秒", self.trim_tail_max)])
        self._add_setting_row(process_grid, 2, self.speed_enabled, [("最小值", self.speed_min), ("最大值", self.speed_max)])
        self._add_setting_row(process_grid, 3, self.crop_enabled, [("最小%", self.crop_min), ("最大%", self.crop_max)])
        self._add_setting_row(process_grid, 4, self.pink_enabled, [("强度", self.pink_strength)])
        self._add_setting_row(process_grid, 5, self.frame_drop_enabled, [("强度", self.frame_drop_strength)])
        self._add_setting_row(process_grid, 6, self.light_sweep, [])
        self._add_setting_row(process_grid, 7, self.edge_guard_enabled, [("像素", self.edge_guard_pixels)])
        self._add_setting_row(process_grid, 8, QLabel("任务设置"), [("并发数", self.max_concurrent), ("硬件模式", self.hardware)])

        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(8)
        video_layout.addWidget(self.auto_process)
        video_layout.addLayout(process_grid)
        tip = QLabel("下载完成后可自动生成处理后视频；原视频保留，处理后视频会在素材库显示\u201c已处理\u201d。")
        tip.setObjectName("PageSubtitle")
        video_layout.addWidget(tip)
        video_actions = QHBoxLayout()
        video_actions.addWidget(make_button("重置视频处理参数", self.reset_video_processing))
        video_actions.addStretch()
        video_layout.addLayout(video_actions)
        video_group = self._settings_group("视频处理", video_layout)

        buttons = QHBoxLayout()
        for button in [
            make_button("保存", self.save, primary=True),
            make_button("刷新", self.load),
        ]:
            buttons.addWidget(button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("系统设置", "代理、YouTube Cookie 和视频处理参数"))
        layout.addWidget(proxy_group)
        layout.addWidget(cookie_group)
        layout.addWidget(video_group)
        layout.addLayout(buttons)
        layout.addStretch()

        # Connect all value-change signals for dirty tracking
        self._connect_dirty_signals()

    def _connect_dirty_signals(self):
        """Connect value-changed signals to mark settings as dirty."""
        self.proxy.textChanged.connect(self._mark_dirty)
        self.auto_process.stateChanged.connect(self._mark_dirty)
        for checkbox in (
            self.trim_head_enabled, self.trim_tail_enabled,
            self.speed_enabled, self.crop_enabled,
            self.pink_enabled, self.light_sweep,
            self.frame_drop_enabled, self.edge_guard_enabled,
        ):
            checkbox.stateChanged.connect(self._mark_dirty)
        for spinbox in (
            self.trim_head_min, self.trim_head_max,
            self.trim_tail_min, self.trim_tail_max,
            self.speed_min, self.speed_max,
            self.crop_min, self.crop_max,
            self.pink_strength, self.frame_drop_strength,
            self.edge_guard_pixels, self.max_concurrent,
        ):
            spinbox.valueChanged.connect(self._mark_dirty)
        self.hardware.currentIndexChanged.connect(self._mark_dirty)

    def _mark_dirty(self):
        self._dirty = True

    def check_unsaved(self) -> bool:
        """Check for unsaved changes and prompt user. Returns True if safe to proceed."""
        if not self._dirty:
            return True
        reply = QMessageBox.question(
            self, "未保存的更改",
            "设置已修改但未保存，是否放弃更改？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _double_spin(self, minimum: float, maximum: float, step: float) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setDecimals(2)
        widget.setFixedWidth(90)
        return widget

    def _settings_group(self, title: str, child_layout) -> QGroupBox:
        group = QGroupBox(title)
        group.setLayout(child_layout)
        return group

    def _add_setting_row(self, grid: QGridLayout, row: int, leader: QWidget, fields: list[tuple[str, QWidget]]) -> None:
        grid.addWidget(leader, row, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        column = 1
        for label, widget in fields:
            grid.addWidget(QLabel(label), row, column, alignment=Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(widget, row, column + 1, alignment=Qt.AlignLeft | Qt.AlignVCenter)
            column += 2
        while column < 5:
            spacer = QLabel("")
            grid.addWidget(spacer, row, column)
            column += 1

    def load(self):
        settings = self.settings_service.get_settings()
        config = settings.get("videoProcessing", {})
        self.proxy.setText(settings.get("downloadProxy") or "")
        self.cookie_status.setText(settings.get("youtubeCookieFileName") or "未配置")
        self.auto_process.setChecked(bool(config.get("autoProcess", True)))
        trim_enabled = bool(config.get("trimEnabled", True))
        self.trim_head_enabled.setChecked(trim_enabled)
        self.trim_tail_enabled.setChecked(trim_enabled)
        self.trim_head_min.setValue(float(config.get("trimHeadMin", 0.3)))
        self.trim_head_max.setValue(float(config.get("trimHeadMax", 1.2)))
        self.trim_tail_min.setValue(float(config.get("trimTailMin", 0.3)))
        self.trim_tail_max.setValue(float(config.get("trimTailMax", 1.2)))
        self.speed_enabled.setChecked(bool(config.get("speedEnabled", True)))
        self.speed_min.setValue(float(config.get("speedMin", 0.97)))
        self.speed_max.setValue(float(config.get("speedMax", 1.03)))
        self.crop_enabled.setChecked(bool(config.get("cropEnabled", True)))
        self.crop_min.setValue(float(config.get("cropPercentMin", 1.0)))
        self.crop_max.setValue(float(config.get("cropPercentMax", 3.0)))
        self.pink_enabled.setChecked(bool(config.get("pinkFilterEnabled", True)))
        self.pink_strength.setValue(float(config.get("pinkFilterStrength", 0.12)))
        self.light_sweep.setChecked(bool(config.get("lightSweep", True)))
        self.frame_drop_enabled.setChecked(bool(config.get("frameDropEnabled", True)))
        self.frame_drop_strength.setValue(float(config.get("frameDropStrength", 0.02)))
        self.edge_guard_enabled.setChecked(bool(config.get("edgeGuardEnabled", True)))
        self.edge_guard_pixels.setValue(int(config.get("edgeGuardPixels", 8)))
        self.max_concurrent.setValue(int(config.get("maxConcurrent", 4)))
        self.hardware.setCurrentText(config.get("hardwareMode", "cpu"))
        self._dirty = False

    def save(self):
        self.settings_service.save_settings(
            self.proxy.text(),
            self._video_processing_payload(),
        )
        self._dirty = False
        self.event_bus.settings_changed.emit()
        self.load()

    def reset_video_processing(self):
        from myUtils.video_processor import DEFAULT_VIDEO_PROCESSING_CONFIG

        self.settings_service.save_settings(self.proxy.text(), dict(DEFAULT_VIDEO_PROCESSING_CONFIG))
        self._dirty = False
        self.event_bus.settings_changed.emit()
        self.load()

    def _video_processing_payload(self) -> dict:
        return {
            "autoProcess": self.auto_process.isChecked(),
            "trimEnabled": self.trim_head_enabled.isChecked() or self.trim_tail_enabled.isChecked(),
            "trimHeadMin": self.trim_head_min.value(),
            "trimHeadMax": self.trim_head_max.value(),
            "trimTailMin": self.trim_tail_min.value(),
            "trimTailMax": self.trim_tail_max.value(),
            "speedEnabled": self.speed_enabled.isChecked(),
            "speedMin": self.speed_min.value(),
            "speedMax": self.speed_max.value(),
            "cropEnabled": self.crop_enabled.isChecked(),
            "cropPercentMin": self.crop_min.value(),
            "cropPercentMax": self.crop_max.value(),
            "pinkFilterEnabled": self.pink_enabled.isChecked(),
            "pinkFilterStrength": self.pink_strength.value(),
            "lightSweep": self.light_sweep.isChecked(),
            "frameDropEnabled": self.frame_drop_enabled.isChecked(),
            "frameDropStrength": self.frame_drop_strength.value(),
            "edgeGuardEnabled": self.edge_guard_enabled.isChecked(),
            "edgeGuardPixels": self.edge_guard_pixels.value(),
            "maxConcurrent": self.max_concurrent.value(),
            "hardwareMode": self.hardware.currentText(),
        }

    def import_youtube_cookie(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 cookies.txt", "", "Text (*.txt)")
        if path:
            self.settings_service.upload_youtube_cookie(Path(path))
            self.event_bus.settings_changed.emit()
            self.load()

    def clear_youtube_cookie(self):
        self.settings_service.clear_youtube_cookie()
        self.event_bus.settings_changed.emit()
        self.load()
