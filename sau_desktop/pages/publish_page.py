"""发布中心页面."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sau_core.services import AccountService, MaterialService, PLATFORM_CHOICES, PublishService
from sau_desktop._shared import DenseTable, EventBus, make_button, page_header, run_background


class PublishPage(QWidget):
    def __init__(self, material_service: MaterialService, account_service: AccountService, publish_service: PublishService, event_bus: EventBus):
        super().__init__()
        self.material_service = material_service
        self.account_service = account_service
        self.publish_service = publish_service
        self.event_bus = event_bus
        self.materials = DenseTable(["ID", "文件名", "路径"], [70, 300, 460])
        self.accounts = DenseTable(["ID", "平台", "用户名"], [70, 100, 220])
        self.platform = QComboBox()
        for value, text in PLATFORM_CHOICES:
            self.platform.addItem(text, value)
        self.title = QLineEdit()
        self.title.setPlaceholderText("发布标题")
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("话题，逗号分隔")
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        top = QSplitter(Qt.Horizontal)
        top.addWidget(self.materials)
        top.addWidget(self.accounts)
        top.setSizes([760, 360])

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("平台", self.platform)
        form.addRow("标题", self.title)
        form.addRow("话题", self.tags)

        actions = QHBoxLayout()
        actions.addWidget(make_button("发布选中任务", self.publish, primary=True))
        actions.addWidget(make_button("刷新", self.refresh))
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("发布中心", "选择素材、账号和平台后提交发布任务"))
        layout.addWidget(top, 1)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.log)

        self.event_bus.accounts_changed.connect(self.refresh)
        self.event_bus.materials_changed.connect(self.refresh)

    def refresh(self):
        self.materials.set_rows([[m.get("id"), m.get("filename"), m.get("file_path")] for m in self.material_service.list_materials()])
        self.accounts.set_rows([[a.get("id"), a.get("platform"), a.get("userName")] for a in self.account_service.list_accounts()])

    def publish(self):
        material_row = self.materials.currentRow()
        account_row = self.accounts.currentRow()
        if material_row < 0 or account_row < 0:
            QMessageBox.warning(self, "发布", "请先选择素材和账号")
            return
        payload = {
            "type": self.platform.currentData(),
            "fileList": [self.materials.item(material_row, 2).text()],
            "accountList": [self.accounts.item(account_row, 2).text()],
            "title": self.title.text().strip(),
            "tags": [tag.strip().lstrip("#") for tag in self.tags.text().split(",") if tag.strip()],
        }
        run_background(
            self,
            lambda: self.publish_service.publish(payload),
            lambda _: self.log.append("发布任务已提交"),
            lambda error: self.log.append(f"发布失败: {error}"),
        )
