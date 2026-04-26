"""素材管理页面."""

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
)

from sau_core.services import MaterialService
from sau_desktop._shared import DebouncedSearch, DenseTable, EventBus, make_button, page_header


class MaterialPage(QWidget):
    def __init__(self, material_service: MaterialService, event_bus: EventBus):
        super().__init__()
        self.material_service = material_service
        self.event_bus = event_bus
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文件名、标题、来源、路径")
        DebouncedSearch(self.search, self.refresh)
        self.table = DenseTable(["ID", "UUID", "文件名", "来源", "标题", "大小", "时间", "路径"], [70, 120, 220, 100, 220, 80, 155, 360])

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        for button in [
            make_button("导入素材", self.import_materials, primary=True),
            make_button("打开预览", self.open_preview),
            make_button("删除", self.delete_material, danger=True),
            make_button("刷新", self.refresh),
        ]:
            toolbar.addWidget(button)
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("素材管理", "本地素材、下载结果和处理后视频统一管理"))
        layout.addWidget(self.search)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)

        self.event_bus.materials_changed.connect(self.refresh)

    def selected_material(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return {"id": int(self.table.item(row, 0).text()), "file_path": self.table.item(row, 7).text()}

    def refresh(self):
        keyword = self.search.text().strip().lower()
        rows = []
        for material in self.material_service.list_materials():
            title = material.get("video_title_zh") or material.get("video_title") or ""
            values = [
                material.get("id"),
                material.get("uuid"),
                material.get("filename"),
                material.get("source_type") or material.get("material_type") or "本地",
                title,
                material.get("filesize"),
                material.get("upload_time"),
                material.get("file_path"),
            ]
            if not keyword or keyword in " ".join(str(value).lower() for value in values):
                rows.append(values)
        self.table.set_rows(rows)

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
            try:
                ids.append(int(self.table.item(row, 0).text()))
            except (ValueError, AttributeError):
                pass
        if not ids:
            return
        if QMessageBox.question(self, "批量删除", f"确定删除 {len(ids)} 个素材？") == QMessageBox.Yes:
            for mid in ids:
                self.material_service.delete_material(mid)
            self.event_bus.materials_changed.emit()
