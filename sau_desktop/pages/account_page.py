"""账号管理页面及登录对话框."""

from __future__ import annotations

import asyncio
import base64

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from sau_core.services import AccountService
from sau_desktop._shared import DenseTable, make_button, page_header, run_background


class AccountPage(QWidget):
    def __init__(self, account_service: AccountService):
        super().__init__()
        self.account_service = account_service
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索账号、平台、Cookie")
        self.search.textChanged.connect(self.refresh)
        self.table = DenseTable(["ID", "平台", "用户名", "Cookie", "状态"], [70, 100, 180, 360, 100])

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        for button in [
            make_button("添加账号", self.add_account, primary=True),
            make_button("校验 Cookie", self.validate_accounts, primary=True),
            make_button("导入 Cookie", self.import_cookie),
            make_button("打开 Cookie", self.open_cookie),
            make_button("删除账号", self.delete_account, danger=True),
            make_button("刷新", self.refresh),
        ]:
            toolbar.addWidget(button)
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("账号管理", "维护各平台账号 Cookie 和校验状态"))
        layout.addWidget(self.search)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)
        self.refresh()

    def selected_account(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return {"id": int(self.table.item(row, 0).text()), "filePath": self.table.item(row, 3).text()}

    def refresh(self):
        keyword = self.search.text().strip().lower()
        rows = []
        for account in self.account_service.list_accounts():
            values = [
                account.get("id"),
                account.get("platform"),
                account.get("userName"),
                account.get("filePath"),
                "正常" if account.get("status") else "未验证",
            ]
            if not keyword or keyword in " ".join(str(value).lower() for value in values):
                rows.append(values)
        self.table.set_rows(rows)

    def add_account(self):
        dialog = AccountLoginDialog(self.account_service, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def validate_accounts(self):
        def work():
            return asyncio.run(self.account_service.list_validated_accounts())

        run_background(self, work, lambda _: self.refresh())

    def import_cookie(self):
        account = self.selected_account()
        if not account:
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择 Cookie JSON", "", "JSON (*.json)")
        if path:
            self.account_service.import_cookie(account["id"], Path(path))
            self.refresh()

    def open_cookie(self):
        account = self.selected_account()
        if not account:
            return
        path = self.account_service.export_cookie_path(account["filePath"])
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def delete_account(self):
        account = self.selected_account()
        if not account:
            return
        if QMessageBox.question(self, "确认删除", "删除选中账号和 Cookie 文件？") == QMessageBox.Yes:
            self.account_service.delete_account(account["id"])
            self.refresh()


class AccountLoginDialog(QDialog):
    login_message = Signal(str)

    PLATFORM_OPTIONS = [("小红书", 1), ("视频号", 2), ("抖音", 3), ("快手", 4)]

    def __init__(self, account_service: AccountService, parent=None):
        super().__init__(parent)
        self.account_service = account_service
        self.setWindowTitle("添加账号")
        self.setMinimumWidth(460)
        self.platform = QComboBox()
        for label, value in self.PLATFORM_OPTIONS:
            self.platform.addItem(label, value)
        self.username = QLineEdit()
        self.username.setPlaceholderText("请输入账号名称")
        self.status = QLabel("选择平台并输入名称后开始登录")
        self.status.setObjectName("PageSubtitle")
        self.qrcode = QLabel("二维码将在这里显示")
        self.qrcode.setAlignment(Qt.AlignCenter)
        self.qrcode.setMinimumHeight(220)
        self.qrcode.setObjectName("PreviewPlaceholder")
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.buttons.button(QDialogButtonBox.Ok).setText("开始登录")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self.start_login)
        self.buttons.rejected.connect(self.reject)
        self.login_message.connect(self._handle_login_message)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("平台", self.platform)
        form.addRow("名称", self.username)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(self.qrcode)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

    def start_login(self):
        username = self.username.text().strip()
        if not username:
            QMessageBox.warning(self, "添加账号", "请输入账号名称")
            return
        self.platform.setEnabled(False)
        self.username.setEnabled(False)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.status.setText("正在请求登录二维码...")
        self.account_service.start_login(
            int(self.platform.currentData()),
            username,
            callback=lambda event: self.login_message.emit(str(event.get("message", ""))),
        )

    def _handle_login_message(self, message: str):
        if message == "200":
            self.status.setText("添加成功，正在刷新账号列表...")
            self.accept()
            return
        if message == "500":
            self.status.setText("添加失败，请稍后重试")
            self.platform.setEnabled(True)
            self.username.setEnabled(True)
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
            return
        if self._set_qrcode_image(message):
            self.status.setText("请使用对应平台 App 扫描二维码登录")
        else:
            self.status.setText("已收到登录二维码数据，请在打开的浏览器窗口中完成登录")
            self.qrcode.setText("请在浏览器中扫码登录")

    def _set_qrcode_image(self, message: str) -> bool:
        data = message.strip()
        if not data:
            return False
        if data.startswith("data:image") and "," in data:
            data = data.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(data, validate=False)
        except Exception:
            return False
        pixmap = QPixmap()
        if not pixmap.loadFromData(image_bytes):
            return False
        self.qrcode.setPixmap(pixmap.scaled(210, 210, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return True
