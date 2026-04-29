"""发布中心页面 — 上下布局 + 隐藏ID + 可折叠日志."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from sau_core.services import AccountService, MaterialService, PublishService
from sau_desktop._shared import (
    DenseTable, EventBus, make_button, page_header, run_background,
    CollapsibleSection,
)


TOPIC_PRESETS = {
    "AI / 自动化": ["AI", "自动化", "效率工具", "副业", "内容创作"],
    "技术 / 编程": ["编程", "开源", "Python", "开发工具", "技术分享"],
    "游戏 / 魔兽": ["魔兽世界", "游戏日常", "怀旧服", "网游", "游戏剪辑"],
    "生活 / Vlog": ["生活记录", "日常", "Vlog", "治愈", "分享"],
    "知识 / 干货": ["干货", "经验分享", "学习", "认知", "成长"],
    "影视 / 剪辑": ["影视剪辑", "电影", "剧情", "高燃", "解说"],
}


class PublishPage(QWidget):
    def __init__(self, material_service: MaterialService, account_service: AccountService, publish_service: PublishService, event_bus: EventBus):
        super().__init__()
        self.material_service = material_service
        self.account_service = account_service
        self.publish_service = publish_service
        self.event_bus = event_bus

        # P0: 隐藏 ID 列和路径列，用户只需看文件名
        self.materials = DenseTable(["文件名", "来源"], [360, 120])
        # P0: 隐藏 ID 列，增加状态列便于识别可用账号
        self.accounts = DenseTable(["平台", "用户名", "状态"], [100, 160, 80])

        self.title = QLineEdit()
        self.title.setPlaceholderText("发布标题")
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("话题，逗号分隔")
        self.topic_preset = QComboBox()
        self.topic_preset.addItem("选择内置话题", [])
        for name, topics in TOPIC_PRESETS.items():
            self.topic_preset.addItem(name, topics)
        topic_widget = QWidget()
        topic_row = QHBoxLayout(topic_widget)
        topic_row.setContentsMargins(0, 0, 0, 0)
        topic_row.addWidget(self.topic_preset, 1)
        topic_row.addWidget(make_button("添加话题", self.add_topic_preset))

        # P2: 日志区域默认折叠
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        log_section = CollapsibleSection("运行日志", self.log, expanded=False)

        # 步骤标签
        step1_label = QLabel("\U0001f4e6 选择素材")
        step1_label.setStyleSheet("font-weight: 700; color: #2563eb; font-size: 13px;")
        step2_label = QLabel("\U0001f464 选择账号")
        step2_label.setStyleSheet("font-weight: 700; color: #2563eb; font-size: 13px;")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("标题", self.title)
        form.addRow("话题预设", topic_widget)
        form.addRow("话题", self.tags)

        actions = QHBoxLayout()
        actions.addWidget(make_button("发布选中任务", self.publish, primary=True))
        actions.addWidget(make_button("刷新", self.refresh))
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(page_header("发布中心", "选择素材和账号后提交发布任务"))
        layout.addWidget(step1_label)
        layout.addWidget(self.materials, 1)
        layout.addWidget(step2_label)
        layout.addWidget(self.accounts, 1)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(log_section)

        self.event_bus.accounts_changed.connect(self.refresh)
        self.event_bus.materials_changed.connect(self.refresh)

    def refresh(self):
        materials = self.material_service.list_materials()
        accounts = self.account_service.list_accounts()
        self.materials.set_rows(
            [[m.get("filename"), m.get("source_type") or "本地"] for m in materials],
            payloads=materials,
        )
        self.accounts.set_rows(
            [[a.get("platform"), a.get("userName"), "正常" if a.get("status") else "未验证"] for a in accounts],
            payloads=accounts,
        )

    def publish(self):
        payloads = self._selected_publish_payloads()
        if not payloads:
            return
        run_background(
            self,
            lambda: [self.publish_service.publish(payload) for payload in payloads],
            lambda _: self.log.append(f"发布任务已提交：{len(payloads)} 个平台"),
            lambda error: self.log.append(f"发布失败: {error}"),
        )

    def add_topic_preset(self):
        preset_topics = self.topic_preset.currentData() or []
        if not preset_topics:
            return
        tags = self._parse_tags()
        for topic in preset_topics:
            if topic not in tags:
                tags.append(topic)
        self.tags.setText(", ".join(tags))

    def _selected_publish_payloads(self) -> list[dict]:
        material_rows = self.materials.checked_rows()
        account_rows = self.accounts.checked_rows()
        if not material_rows or not account_rows:
            QMessageBox.warning(self, "发布", "请先选择素材和账号")
            return []
        # P0: 使用 payload 而非表格文本获取数据（避免截断问题）
        materials = [self.materials.get_payload(row) for row in material_rows]
        accounts = [self.accounts.get_payload(row) for row in account_rows]
        file_list = [item.get("file_path") for item in materials if item and item.get("file_path")]
        if not file_list:
            QMessageBox.warning(self, "发布", "选中的素材缺少文件路径")
            return []
        accounts_by_platform: dict[int, list[str]] = {}
        for account in accounts:
            if not account or not account.get("filePath") or not account.get("type"):
                continue
            accounts_by_platform.setdefault(int(account["type"]), []).append(account["filePath"])
        if not accounts_by_platform:
            QMessageBox.warning(self, "发布", "选中的账号缺少平台信息")
            return []
        return [
            {
                "type": platform_type,
                "fileList": file_list,
                "accountList": account_list,
                "title": self.title.text().strip(),
                "tags": self._parse_tags(),
            }
            for platform_type, account_list in accounts_by_platform.items()
        ]

    def _parse_tags(self) -> list[str]:
        return [tag.strip().lstrip("#") for tag in self.tags.text().split(",") if tag.strip()]
