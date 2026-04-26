"""素材管理页面 — 精简列 + 选择状态栏 + 按钮重排."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from sau_core.services import MaterialService
from sau_desktop._shared import (
    DebouncedSearch, DenseTable, EventBus, make_button, page_header,
)


class MaterialPage(QWidget):
    def __init__(self, material_service: MaterialService, event_bus: EventBus):
        super().__init__()
        self.material_service = material_service
        self.event_bus = event_bus
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文件名、标题、来源...")
        DebouncedSearch(self.search, self.refresh)

        # P0: 从 8 列精简为 5 列，移除 ID/UUID/路径（用户不需要看到）
        #     文件名加宽到 300px 避免截断
        self.table = DenseTable(
            ["文件名", "来源", "标题", "大小", "时间"],
            [300, 80, 260, 75, 155],
        )

        # P2: 选中数量状态栏
        self.selection_label = QLabel("")
        self.selection_label.setObjectName("SelectionInfo")

        # P1/P2: 工具栏按主次频率重新排列
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        for button in [
            make_button("导入素材", self.import_materials, primary=True),
            make_button("刷新", self.refresh),
            make_button("打开预览", self.open_preview),
            make_button("删除", self.delete_material, danger=True),
        ]:
            toolbar.addWidget(button)
        toolbar.addStretch()
        toolbar.addWidget(self.selection_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("素材管理", "本地素材、下载结果和处理后视频统一管理"))
        layout.addWidget(self.search)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)

        # P2: 连接选择变化信号更新状态栏
        self.table.selection_changed.connect(self._update_selection_info)

        self.event_bus.materials_changed.connect(self.refresh)

    def _update_selection_info(self, count: int):
        """P2: 显示当前选中数量"""
        if count > 0:
            self.selection_label.setText(f"已选 {count} 项")
        else:
            self.selection_label.setText("")

    def selected_material(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        payload = self.table.get_payload(row)
        if payload and isinstance(payload, dict):
            return {"id": payload.get("id"), "file_path": payload.get("file_path")}
        return None

    def refresh(self):
        keyword = self.search.text().strip().lower()
        rows = []
        payloads = []
        for material in self.material_service.list_materials():
            title = material.get("video_title_zh") or material.get("video_title") or ""
            values = [
                material.get("filename"),
                material.get("source_type") or material.get("material_type") or "本地",
                title,
                material.get("filesize"),
                material.get("upload_time"),
            ]
            if not keyword or keyword in " ".join(str(v).lower() for v in values):
                rows.append(values)
                payloads.append(material)  # 存储完整数据作为 payload
        self.table.set_rows(rows, payloads=payloads)

    def import_materials(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择素材")
        if paths:
            self.material_service.import_files([Path(path) for path in paths])
            self.event_bus.materials_changed.emit()

    def open_preview(self):
        material = self.selected_material()
        if not material:
            return
        path = self.material_service.resolve_material_path(material["file_path"])
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def delete_material(self):
        checked = self.table.checked_rows()
        if not checked:
            material = self.selected_material()
            if not material:
                return
            if QMessageBox.question(self, "确认删除", "删除选中素材文件和记录？") == QMessageBox.Yes:
                self.material_service.delete_material(material["id"])
                self.event_bus.materials_changed.emit()
            return
        ids = []
        for row in checked:
            payload = self.table.get_payload(row)
            if payload and isinstance(payload, dict) and payload.get("id"):
                ids.append(payload["id"])
        if not ids:
            return
        if QMessageBox.question(self, "批量删除", f"确定删除 {len(ids)} 个素材？") == QMessageBox.Yes:
            for mid in ids:
                self.material_service.delete_material(mid)
            self.event_bus.materials_changed.emit()
