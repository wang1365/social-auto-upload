"""仪表盘页面 — KPI卡片化 + 表格精简."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QHBoxLayout

from sau_core.services import AccountService, MaterialService
from sau_desktop._shared import (
    DenseTable, EventBus, make_button, page_header, kpi_card,
)


class DashboardPage(QWidget):
    def __init__(self, account_service: AccountService, material_service: MaterialService, event_bus: EventBus):
        super().__init__()
        self.account_service = account_service
        self.material_service = material_service
        self.event_bus = event_bus

        # P1: KPI 卡片区域（替代纯文本）
        self.kpi_container = QWidget()
        self.kpi_layout = QHBoxLayout(self.kpi_container)
        self.kpi_layout.setContentsMargins(0, 0, 0, 0)
        self.kpi_layout.setSpacing(12)
        self.kpi_cards: list[QLabel] = []
        for i in range(4):
            card = kpi_card("0", "", color_index=i)
            self.kpi_layout.addWidget(card)
            self.kpi_cards.append(card)

        # P0: 隐藏 ID 列，只显示用户关心的信息
        self.recent_table = DenseTable(
            ["文件名", "来源", "大小(MB)", "时间"],
            [340, 100, 90, 170],
        )
        refresh = make_button("刷新", self.refresh, primary=True)

        # 工具栏：按钮紧跟刷新
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(refresh)
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(page_header("仪表盘", "账号、平台和素材库存概览"))
        layout.addWidget(self.kpi_container)
        layout.addLayout(toolbar)
        layout.addWidget(self.recent_table, 1)

        self.event_bus.accounts_changed.connect(self.refresh)
        self.event_bus.materials_changed.connect(self.refresh)

    def refresh(self):
        accounts = self.account_service.list_accounts()
        materials = self.material_service.list_materials()
        platforms = len({item.get("type") for item in accounts})
        videos = sum(1 for item in materials if str(item.get("filename", "")).lower().endswith((".mp4", ".mov", ".mkv", ".avi")))

        # 更新 KPI 卡片
        kpi_data = [
            (str(len(accounts)), "账号"),
            (str(platforms), "平台"),
            (str(len(materials)), "素材"),
            (str(videos), "视频"),
        ]
        for card, (value, label) in zip(self.kpi_cards, kpi_data):
            # 找到卡片内的 value 和 label 标签并更新
            for child in card.children():
                if isinstance(child, QLabel):
                    if child.objectName() == "KpiValue":
                        child.setText(value)
                    elif child.objectName() == "KpiLabel":
                        child.setText(label)

        # P0: 不再显示 ID 列
        self.recent_table.set_rows([
            [
                m.get("filename"),
                m.get("source_type") or "本地",
                m.get("filesize"),
                m.get("upload_time"),
            ]
            for m in materials[:30]
        ])
