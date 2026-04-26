"""仪表盘页面."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout

from sau_core.services import AccountService, MaterialService
from sau_desktop._shared import DenseTable, EventBus, make_button, page_header


class DashboardPage(QWidget):
    def __init__(self, account_service: AccountService, material_service: MaterialService, event_bus: EventBus):
        super().__init__()
        self.account_service = account_service
        self.material_service = material_service
        self.event_bus = event_bus
        self.kpis = QLabel()
        self.kpis.setObjectName("Kpi")
        self.recent_table = DenseTable(["ID", "文件名", "来源", "大小(MB)", "时间"], [70, 360, 120, 100, 180])
        refresh = make_button("刷新", self.refresh, primary=True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("仪表盘", "账号、平台和素材库存概览"))
        layout.addWidget(self.kpis)
        layout.addWidget(refresh, alignment=Qt.AlignLeft)
        layout.addWidget(self.recent_table, 1)

        self.event_bus.accounts_changed.connect(self.refresh)
        self.event_bus.materials_changed.connect(self.refresh)

    def refresh(self):
        accounts = self.account_service.list_accounts()
        materials = self.material_service.list_materials()
        platforms = len({item.get("type") for item in accounts})
        videos = sum(1 for item in materials if str(item.get("filename", "")).lower().endswith((".mp4", ".mov", ".mkv", ".avi")))
        self.kpis.setText(f"账号 {len(accounts)}    平台 {platforms}    素材 {len(materials)}    视频 {videos}")
        self.recent_table.set_rows([
            [m.get("id"), m.get("filename"), m.get("source_type") or "本地", m.get("filesize"), m.get("upload_time")]
            for m in materials[:30]
        ])
