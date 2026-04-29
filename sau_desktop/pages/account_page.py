"""账号管理页面及登录对话框 — 精简列 + payload + 选择状态栏."""

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

from sau_core.services import AccountService, PLATFORM_CHOICES
from sau_desktop._shared import (
    DebouncedSearch, DenseTable, EventBus, make_button, page_header, run_background,
    status_dot,
)


class AccountPage(QWidget):
    def __init__(self, account_service: AccountService, event_bus: EventBus):
        super().__init__()
        self.account_service = account_service
        self.event_bus = event_bus
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索账号、平台...")
        DebouncedSearch(self.search, self.refresh)

        # P0: 隐藏 ID 列和 Cookie 路径列（路径太长且用户不需要看）
        #     状态用颜色指示器更直观
        self.table = DenseTable(["平台", "用户名", "状态"], [100, 180, 80])

        # P2: 选中数量状态栏
        self.selection_label = QLabel("")
        self.selection_label.setObjectName("SelectionInfo")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        for button in [
            make_button("添加账号", self.add_account, primary=True),
            make_button("刷新", self.refresh),
            make_button("校验 Cookie", self.validate_accounts, primary=True),
            make_button("导入 Cookie", self.import_cookie),
            make_button("打开 Cookie", self.open_cookie),
            make_button("删除账号", self.delete_account, danger=True),
        ]:
            toolbar.addWidget(button)
        toolbar.addStretch()
        toolbar.addWidget(self.selection_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("账号管理", "维护各平台账号 Cookie 和校验状态"))
        layout.addWidget(self.search)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)

        # P2: 连接选择变化信号
        self.table.selection_changed.connect(self._update_selection_info)

        self.event_bus.accounts_changed.connect(self.refresh)

    def _update_selection_info(self, count: int):
        if count > 0:
            self.selection_label.setText(f"已选 {count} 项")
        else:
            self.selection_label.setText("")

    def selected_account(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        # P0: 使用 payload 获取完整数据
        payload = self.table.get_payload(row)
        if payload and isinstance(payload, dict):
            return {"id": payload.get("id"), "filePath": payload.get("filePath")}
        return None

    def refresh(self):
        keyword = self.search.text().strip().lower()
        rows = []
        payloads = []
        for account in self.account_service.list_accounts():
            is_ok = bool(account.get("status"))
            status_text = "正常" if is_ok else "未验证"
            values = [
                account.get("platform"),
                account.get("userName"),
                status_text,
            ]
            if not keyword or keyword in " ".join(str(v).lower() for v in values):
                rows.append(values)
                payloads.append(account)
        self.table.set_rows(rows, payloads=payloads)

    def add_account(self):
        dialog = AccountLoginDialog(self.account_service, self)
        if dialog.exec() == QDialog.Accepted:
            self.event_bus.accounts_changed.emit()

    def validate_accounts(self):
        def work():
            return asyncio.run(self.account_service.list_validated_accounts())

        run_background(self, work, lambda _: self.event_bus.accounts_changed.emit())

    def import_cookie(self):
        account = self.selected_account()
        if not account:
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择 Cookie JSON", "", "JSON (*.json)")
        if path:
            self.account_service.import_cookie(account["id"], Path(path))
            self.event_bus.accounts_changed.emit()

    def open_cookie(self):
        account = self.selected_account()
        if not account:
            return
        path = self.account_service.export_cookie_path(account["filePath"])
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def delete_account(self):
        checked = self.table.checked_rows()
        if not checked:
            account = self.selected_account()
            if not account:
                return
            if QMessageBox.question(self, "确认删除", "删除选中账号和 Cookie 文件？") == QMessageBox.Yes:
                self.account_service.delete_account(account["id"])
                self.event_bus.accounts_changed.emit()
            return
        ids = []
        for row in checked:
            payload = self.table.get_payload(row)
            if payload and isinstance(payload, dict) and payload.get("id"):
                ids.append(payload["id"])
        if not ids:
            return
        if QMessageBox.question(self, "批量删除", f"确定删除 {len(ids)} 个账号？") == QMessageBox.Yes:
            for aid in ids:
                self.account_service.delete_account(aid)
            self.event_bus.accounts_changed.emit()


class AccountLoginDialog(QDialog):
    login_message = Signal(str)

    def __init__(self, account_service: AccountService, parent=None):
        super().__init__(parent)
        self.account_service = account_service
        self._login_active = True
        self.setWindowTitle("添加账号")
        self.setMinimumWidth(460)
        self.platform = QComboBox()
        for value, label in PLATFORM_CHOICES:
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
        self.buttons.rejected.connect(self._cancel_login)
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

    def _cancel_login(self):
        self._login_active = False
        self.reject()

    def closeEvent(self, event):
        self._login_active = False
        super().closeEvent(event)

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
            callback=self._on_login_event,
        )

    def _on_login_event(self, event):
        if not self._login_active:
            return
        self.login_message.emit(str(event.get("message", "")))

    def _handle_login_message(self, message: str):
        if not self._login_active:
            return
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
