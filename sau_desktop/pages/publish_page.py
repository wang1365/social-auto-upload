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

from sau_core.services import AccountService, MaterialService, PLATFORM_CHOICES, PublishService
from sau_desktop._shared import (
    DenseTable, EventBus, make_button, page_header, run_background,
    CollapsibleSection,
)


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

        self.platform = QComboBox()
        for value, text in PLATFORM_CHOICES:
            self.platform.addItem(text, value)
        self.title = QLineEdit()
        self.title.setPlaceholderText("发布标题")
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("话题，逗号分隔")

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
        form.addRow("平台", self.platform)
        form.addRow("标题", self.title)
        form.addRow("话题", self.tags)

        actions = QHBoxLayout()
        actions.addWidget(make_button("发布选中任务", self.publish, primary=True))
        actions.addWidget(make_button("刷新", self.refresh))
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(page_header("发布中心", "选择素材、账号和平台后提交发布任务"))
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
        material_row = self.materials.currentRow()
        account_row = self.accounts.currentRow()
        if material_row < 0 or account_row < 0:
            QMessageBox.warning(self, "发布", "请先选择素材和账号")
            return
        # P0: 使用 payload 而非表格文本获取数据（避免截断问题）
        mat_payload = self.materials.get_payload(material_row)
        acc_payload = self.accounts.get_payload(account_row)
        payload = {
            "type": self.platform.currentData(),
            "fileList": [mat_payload.get("file_path") if mat_payload else self.materials.item(material_row, 0).text()],
            "accountList": [acc_payload.get("filePath") if acc_payload else self.accounts.item(account_row, 1).text()],
            "title": self.title.text().strip(),
            "tags": [tag.strip().lstrip("#") for tag in self.tags.text().split(",") if tag.strip()],
        }
        run_background(
            self,
            lambda: self.publish_service.publish(payload),
            lambda _: self.log.append("发布任务已提交"),
            lambda error: self.log.append(f"发布失败: {error}"),
        )
