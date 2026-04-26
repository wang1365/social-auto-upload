from __future__ import annotations

import base64
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sau_core.services import (
    AccountService,
    DownloadService,
    MaterialService,
    ProcessingService,
    PublishService,
    ServiceError,
    SettingsService,
    VIDEO_DIR,
    ensure_runtime_schema,
)


APP_STYLE = """
QMainWindow, QWidget {
    background: #f5f7fb;
    color: #1f2937;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 12px;
}
QToolBar {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #d9e1ec;
    spacing: 6px;
    padding: 4px 8px;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d9e1ec;
}
QWidget#Sidebar {
    background: #ffffff;
    border-right: 1px solid #d9e1ec;
}
QWidget#BrandBlock {
    background: #ffffff;
    border-bottom: 1px solid #d9e1ec;
}
QLabel#BrandTitle {
    font-size: 18px;
    font-weight: 900;
    color: #14532d;
    letter-spacing: 0px;
    background: #ecfdf5;
    border: 1px solid #bbf7d0;
    border-radius: 6px;
    padding: 4px 8px;
}
QListWidget#Navigation {
    background: #ffffff;
    border: 0;
    padding: 8px 6px;
    outline: 0;
}
QListWidget#Navigation::item {
    min-height: 30px;
    padding: 6px 10px;
    border-radius: 6px;
    color: #334155;
}
QListWidget#Navigation::item:hover {
    background: #eef5ff;
}
QListWidget#Navigation::item:selected {
    background: #dbeafe;
    color: #0f4ea8;
    border-left: 3px solid #2563eb;
    font-weight: 600;
}
QLabel#PageTitle {
    font-size: 19px;
    font-weight: 900;
    color: #134e4a;
}
QLabel#PageSubtitle {
    color: #64748b;
    font-size: 12px;
}
QWidget#PageHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f0fdfa, stop:1 #ffffff);
    border: 1px solid #ccfbf1;
    border-left: 4px solid #0f766e;
    border-radius: 7px;
}
QLabel#PreviewPlaceholder {
    background: #0f172a;
    color: #e5e7eb;
    border: 1px solid #1f2937;
    border-radius: 6px;
    padding: 10px;
}
QLabel#Kpi {
    background: #ffffff;
    border: 1px solid #d9e1ec;
    border-radius: 8px;
    padding: 8px 10px;
    font-weight: 600;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    min-height: 26px;
    padding: 2px 7px;
    selection-background-color: #bfdbfe;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #2563eb;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    min-height: 26px;
    padding: 2px 12px;
}
QPushButton:hover {
    background: #f1f5f9;
    border-color: #94a3b8;
}
QPushButton:pressed {
    background: #e2e8f0;
}
QPushButton#PrimaryButton {
    background: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#DangerButton {
    color: #b42318;
    border-color: #fecaca;
    background: #fff7f7;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #d9e1ec;
    border-radius: 6px;
    gridline-color: #e5e7eb;
    selection-background-color: #dbeafe;
    selection-color: #111827;
}
QHeaderView::section {
    background: #eef2f7;
    color: #334155;
    border: 0;
    border-right: 1px solid #d9e1ec;
    border-bottom: 1px solid #d9e1ec;
    padding: 5px 6px;
    font-weight: 700;
}
QSplitter::handle {
    background: #d9e1ec;
}
QGroupBox {
    border: 1px solid #d5dde8;
    border-radius: 6px;
    margin-top: 10px;
    padding: 10px 10px 8px 10px;
    font-weight: 700;
    color: #111827;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
"""


class Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self):
        try:
            self.finished.emit(self.fn())
        except Exception as exc:
            self.failed.emit(str(exc))


def run_background(parent, fn, on_done=None, on_error=None):
    thread = QThread(parent)
    worker = Worker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(lambda result: on_done(result) if on_done else None)
    worker.failed.connect(lambda message: on_error(message) if on_error else QMessageBox.critical(parent, "错误", message))
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


def make_button(text: str, slot=None, primary=False, danger=False) -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setObjectName("PrimaryButton")
    if danger:
        button.setObjectName("DangerButton")
    if slot:
        button.clicked.connect(slot)
    return button


def page_header(title: str, subtitle: str = "") -> QWidget:
    container = QWidget()
    container.setObjectName("PageHeader")
    layout = QHBoxLayout(container)
    layout.setContentsMargins(12, 6, 12, 6)
    layout.setSpacing(10)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    layout.addWidget(title_label)
    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setAlignment(Qt.AlignVCenter)
        layout.addWidget(subtitle_label)
    layout.addStretch()
    return container


class DenseTable(QTableWidget):
    def __init__(self, headers: list[str], column_widths: list[int] | None = None):
        super().__init__(0, len(headers))
        self.column_widths = column_widths or []
        self.setHorizontalHeaderLabels(headers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(True)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(28)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setMinimumSectionSize(54)
        for index, width in enumerate(self.column_widths):
            self.setColumnWidth(index, width)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_rows(self, rows: list[list[object]], payloads: list[object] | None = None):
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        payloads = payloads or [None] * len(rows)
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                text = "" if value is None else str(value)
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, value)
                item.setData(Qt.UserRole + 1, payloads[row_index])
                item.setToolTip(text)
                self.setItem(row_index, column_index, item)
        for index, width in enumerate(self.column_widths):
            self.setColumnWidth(index, width)
        self.setSortingEnabled(True)


class DashboardPage(QWidget):
    def __init__(self, account_service: AccountService, material_service: MaterialService):
        super().__init__()
        self.account_service = account_service
        self.material_service = material_service
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
        self.refresh()

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
            import asyncio

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


class MaterialPage(QWidget):
    def __init__(self, material_service: MaterialService):
        super().__init__()
        self.material_service = material_service
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文件名、标题、来源、路径")
        self.search.textChanged.connect(self.refresh)
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
        self.refresh()

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
            self.refresh()

    def open_preview(self):
        material = self.selected_material()
        if not material:
            return
        path = self.material_service.resolve_material_path(material["file_path"])
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def delete_material(self):
        material = self.selected_material()
        if not material:
            return
        if QMessageBox.question(self, "确认删除", "删除选中素材文件和记录？") == QMessageBox.Yes:
            self.material_service.delete_material(material["id"])
            self.refresh()


class DownloadPage(QWidget):
    refresh_requested = Signal()

    def __init__(self, download_service: DownloadService):
        super().__init__()
        self.download_service = download_service
        self.refresh_requested.connect(self.refresh)
        self.detail_dialog = None
        self.table = DenseTable(["下载时间", "下载进度", "标题", "分辨率", "文件大小"], [165, 280, 420, 100, 100])
        self.table.doubleClicked.connect(lambda _index: self.open_selected_task_detail())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(make_button("新建下载", self.create_task, primary=True))
        action_row.addWidget(make_button("刷新", self.refresh))
        action_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(page_header("下载中心", "YouTube 下载任务、进度和结果素材"))
        layout.addLayout(action_row)
        layout.addWidget(self.table, 1)
        self.refresh()

    def create_task(self):
        dialog = CreateDownloadDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        url, download_subtitles = dialog.values()
        try:
            task_id = self.download_service.create_youtube_download_task(
                url,
                download_subtitles,
                callback=lambda _: self.refresh_requested.emit(),
            )
            self.refresh()
            self.open_task_detail(task_id)
        except ServiceError as exc:
            QMessageBox.warning(self, "下载失败", str(exc))

    def open_task_detail(self, task_id: str):
        if self.detail_dialog:
            self.detail_dialog.close()
        self.detail_dialog = DownloadTaskDetailDialog(self.download_service, task_id, self)
        self.detail_dialog.show()
        self.detail_dialog.raise_()
        self.detail_dialog.activateWindow()

    def refresh(self):
        tasks = self.download_service.list_youtube_tasks()
        self.table.set_rows(
            [
                [
                    task.get("createdAt") or task.get("updatedAt"),
                    self._progress_text(task),
                    task.get("videoTitleZh") or task.get("videoTitle") or task.get("sourceUrl"),
                    task.get("resolution") or "-",
                    self._file_size_text(task),
                ]
                for task in tasks
            ],
            payloads=tasks,
        )
        if self.detail_dialog and self.detail_dialog.isVisible():
            self.detail_dialog.refresh()

    def selected_task(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        return self.table.item(row, 0).data(Qt.UserRole + 1)

    def open_selected_task_detail(self):
        task = self.selected_task()
        if task and task.get("taskId"):
            self.open_task_detail(task["taskId"])

    def show_context_menu(self, position):
        row = self.table.rowAt(position.y())
        if row >= 0:
            self.table.selectRow(row)
        task = self.selected_task()
        if not task:
            return
        menu = QMenu(self)
        detail_action = menu.addAction("查看详情")
        action = menu.exec(self.table.viewport().mapToGlobal(position))
        if action == detail_action:
            self.open_selected_task_detail()

    def _progress_text(self, task: dict) -> str:
        percent = task.get("progressPercent")
        if isinstance(percent, (int, float)):
            prefix = f"{int(percent)}%"
        elif task.get("status") == "success":
            prefix = "100%"
        else:
            prefix = "-"
        detail = task.get("processingProgressText") or task.get("progressText") or task.get("status") or ""
        return f"{prefix}  {detail}".strip()

    def _file_size_text(self, task: dict) -> str:
        size = task.get("fileSize")
        if isinstance(size, (int, float)):
            return f"{size:.2f} MB"
        total_bytes = task.get("totalBytes")
        if isinstance(total_bytes, (int, float)) and total_bytes > 0:
            return f"{total_bytes / 1024 / 1024:.2f} MB"
        return "-"


class CreateDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建 YouTube 下载")
        self.setMinimumWidth(520)
        self.url = QLineEdit()
        self.url.setPlaceholderText("请输入单个 YouTube 视频链接")
        self.subtitles = QCheckBox("下载字幕")
        self.subtitles.setChecked(True)
        tip = QLabel("下载会自动提取元数据，并将标题翻译为中文后保存。")
        tip.setObjectName("PageSubtitle")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("视频链接", self.url)
        form.addRow("字幕", self.subtitles)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("开始下载")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(tip)
        layout.addWidget(buttons)

    def accept(self):
        if not self.url.text().strip():
            QMessageBox.warning(self, "新建下载", "请输入 YouTube 视频链接")
            return
        super().accept()

    def values(self) -> tuple[str, bool]:
        return self.url.text().strip(), self.subtitles.isChecked()


class DownloadTaskDetailDialog(QDialog):
    def __init__(self, download_service: DownloadService, task_id: str, parent=None):
        super().__init__(parent)
        self.download_service = download_service
        self.task_id = task_id
        self.setWindowTitle("下载详情")
        self.setMinimumSize(760, 520)

        self.status = QLabel()
        self.phase = QLabel()
        self.title = QLabel()
        self.source_url = QLabel()
        self.source_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.filename = QLabel()
        self.updated_at = QLabel()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress_text = QLabel()
        self.speed = QLabel()
        self.eta = QLabel()
        self.error = QTextEdit()
        self.error.setReadOnly(True)
        self.error.setMaximumHeight(100)
        self.description = QTextEdit()
        self.description.setReadOnly(True)
        self.source_preview = self._source_preview_card()
        self.local_preview = self._media_preview_card("已下载视频")
        self.processed_preview = self._media_preview_card("处理后视频")

        summary = QFormLayout()
        summary.setLabelAlignment(Qt.AlignRight)
        summary.addRow("任务 ID", QLabel(task_id))
        summary.addRow("状态", self.status)
        summary.addRow("阶段", self.phase)
        summary.addRow("标题", self.title)
        summary.addRow("视频 URL", self.source_url)
        summary.addRow("本地文件", self.filename)
        summary.addRow("更新时间", self.updated_at)

        progress_layout = QFormLayout()
        progress_layout.setLabelAlignment(Qt.AlignRight)
        progress_layout.addRow("进度", self.progress)
        progress_layout.addRow("说明", self.progress_text)
        progress_layout.addRow("速度", self.speed)
        progress_layout.addRow("剩余时间", self.eta)

        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(10)
        preview_layout.addWidget(self.source_preview["group"], 1)
        preview_layout.addWidget(self.local_preview["group"], 1)
        preview_layout.addWidget(self.processed_preview["group"], 1)

        buttons = QHBoxLayout()
        buttons.addWidget(make_button("刷新", self.refresh))
        buttons.addStretch()
        buttons.addWidget(make_button("关闭", self.close))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(summary)
        layout.addLayout(progress_layout)
        layout.addLayout(preview_layout)
        layout.addWidget(QLabel("视频描述"))
        layout.addWidget(self.description, 1)
        layout.addWidget(QLabel("失败信息"))
        layout.addWidget(self.error)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        try:
            task = self.download_service.get_youtube_task(self.task_id)
        except ServiceError as exc:
            self.status.setText(str(exc))
            return
        title = task.get("videoTitleZh") or task.get("videoTitle") or "-"
        progress_percent = task.get("progressPercent")
        if not isinstance(progress_percent, (int, float)):
            progress_percent = 100 if task.get("status") == "success" else 0

        self.status.setText(task.get("status") or "-")
        self.phase.setText(task.get("phase") or "-")
        self.title.setText(title)
        self.source_url.setText(task.get("sourceUrl") or "-")
        self.filename.setText(task.get("filename") or "-")
        self.updated_at.setText(task.get("updatedAt") or "-")
        self.progress.setValue(max(0, min(100, int(progress_percent))))
        self.progress_text.setText(task.get("progressText") or "-")
        self.speed.setText(task.get("speedText") or "-")
        self.eta.setText(task.get("etaText") or "-")
        self.description.setPlainText(task.get("videoDescription") or "")
        self.error.setPlainText(task.get("errorDetail") or task.get("errorMessage") or "")
        self._update_source_preview(task.get("sourceUrl"))
        self._update_media_preview(
            self.local_preview,
            task.get("filename") or "等待下载完成",
            task.get("filePath"),
        )
        processing_text = task.get("processingProgressText") or "等待视频处理"
        if task.get("processedFilePath"):
            processing_text = task.get("processedFilename") or task.get("processedFilePath")
        self._update_media_preview(
            self.processed_preview,
            processing_text,
            task.get("processedFilePath"),
        )

    def _source_preview_card(self):
        group = QGroupBox("源视频")
        if QApplication.instance() and QApplication.platformName().lower() == "offscreen":
            body = QLabel("测试环境不加载 WebEngine")
            body.setAlignment(Qt.AlignCenter)
            body.setObjectName("PreviewPlaceholder")
            web = None
        else:
            web = QWebEngineView()
            web.setMinimumHeight(150)
            body = web
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(body, 1)
        return {"group": group, "body": body, "web": web, "source_url": None}

    def _media_preview_card(self, title: str):
        group = QGroupBox(title)
        video = QVideoWidget()
        video.setMinimumHeight(150)
        player = QMediaPlayer(self)
        audio = QAudioOutput(self)
        player.setAudioOutput(audio)
        player.setVideoOutput(video)
        placeholder = QLabel("等待视频文件")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setObjectName("PreviewPlaceholder")
        play_button = make_button("播放/暂停")
        stop_button = make_button("停止")
        play_button.setEnabled(False)
        stop_button.setEnabled(False)
        play_button.clicked.connect(lambda: self._toggle_media_player(player))
        stop_button.clicked.connect(player.stop)

        controls = QHBoxLayout()
        controls.addWidget(play_button)
        controls.addWidget(stop_button)
        controls.addStretch()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(video, 1)
        layout.addWidget(placeholder, 1)
        layout.addLayout(controls)
        video.hide()
        return {
            "group": group,
            "video": video,
            "placeholder": placeholder,
            "player": player,
            "play_button": play_button,
            "stop_button": stop_button,
            "file_path": None,
        }

    def _current_task(self) -> dict:
        return self.download_service.get_youtube_task(self.task_id)

    def _update_source_preview(self, source_url: str | None):
        if not source_url:
            if isinstance(self.source_preview["body"], QLabel):
                self.source_preview["body"].setText("等待视频链接")
            return
        if self.source_preview["source_url"] == source_url:
            return
        self.source_preview["source_url"] = source_url
        embed_url = self._youtube_embed_url(source_url)
        web = self.source_preview.get("web")
        if web:
            web.load(QUrl(embed_url or source_url))
        elif isinstance(self.source_preview["body"], QLabel):
            self.source_preview["body"].setText("源视频将在正式窗口中内嵌播放")

    def _update_media_preview(self, preview, text: str, relative_path: str | None):
        if not relative_path:
            preview["player"].stop()
            preview["file_path"] = None
            preview["video"].hide()
            preview["placeholder"].show()
            preview["placeholder"].setText(text)
            preview["play_button"].setEnabled(False)
            preview["stop_button"].setEnabled(False)
            return
        if preview["file_path"] != relative_path:
            preview["player"].stop()
            preview["file_path"] = relative_path
            preview["player"].setSource(QUrl.fromLocalFile(str(VIDEO_DIR / relative_path)))
        preview["placeholder"].hide()
        preview["video"].show()
        preview["play_button"].setEnabled(True)
        preview["stop_button"].setEnabled(True)

    def _toggle_media_player(self, player: QMediaPlayer):
        if player.playbackState() == QMediaPlayer.PlayingState:
            player.pause()
        else:
            player.play()

    def _youtube_embed_url(self, source_url: str) -> str:
        parsed = urlparse(source_url)
        video_id = ""
        if "youtu.be" in parsed.netloc:
            video_id = parsed.path.strip("/").split("/", 1)[0]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        if not video_id:
            return ""
        return f"https://www.youtube.com/embed/{video_id}"

    def closeEvent(self, event):
        for preview in (self.local_preview, self.processed_preview):
            preview["player"].stop()
        super().closeEvent(event)


class PublishPage(QWidget):
    def __init__(self, material_service: MaterialService, account_service: AccountService, publish_service: PublishService):
        super().__init__()
        self.material_service = material_service
        self.account_service = account_service
        self.publish_service = publish_service
        self.materials = DenseTable(["ID", "文件名", "路径"], [70, 300, 460])
        self.accounts = DenseTable(["ID", "平台", "用户名"], [70, 100, 220])
        self.platform = QComboBox()
        for value, text in [(1, "小红书"), (2, "视频号"), (3, "抖音"), (4, "快手")]:
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
        self.refresh()

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


class SettingsPage(QWidget):
    def __init__(self, settings_service: SettingsService, processing_service: ProcessingService):
        super().__init__()
        self.settings_service = settings_service
        self.processing_service = processing_service
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
        tip = QLabel("下载完成后可自动生成处理后视频；原视频保留，处理后视频会在素材库显示“已处理”。")
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
        self.load()

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

    def save(self):
        self.settings_service.save_settings(
            self.proxy.text(),
            self._video_processing_payload(),
        )
        self.load()

    def reset_video_processing(self):
        from myUtils.video_processor import DEFAULT_VIDEO_PROCESSING_CONFIG

        self.settings_service.save_settings(self.proxy.text(), dict(DEFAULT_VIDEO_PROCESSING_CONFIG))
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
            self.load()

    def clear_youtube_cookie(self):
        self.settings_service.clear_youtube_cookie()
        self.load()


class AboutPage(QWidget):
    def __init__(self):
        super().__init__()
        text = QLabel("拾光分发 1.0\n本地 PySide6 客户端\nFlask/Vue Web 主路径已废弃。")
        text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(page_header("关于", "本地客户端版本信息"))
        layout.addWidget(text)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ensure_runtime_schema()
        self.setWindowTitle("拾光分发 1.0")
        self.resize(1320, 820)

        self.account_service = AccountService()
        self.material_service = MaterialService()
        self.processing_service = ProcessingService()
        self.download_service = DownloadService(self.processing_service)
        self.publish_service = PublishService()
        self.settings_service = SettingsService()

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(148)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        brand_block = QWidget()
        brand_block.setObjectName("BrandBlock")
        brand_layout = QVBoxLayout(brand_block)
        brand_layout.setContentsMargins(12, 14, 12, 14)
        brand_layout.setSpacing(0)
        brand = QLabel("拾光分发")
        brand.setObjectName("BrandTitle")
        brand.setAlignment(Qt.AlignCenter)
        brand_layout.addWidget(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("Navigation")
        self.stack = QStackedWidget()
        pages = [
            ("仪表盘", DashboardPage(self.account_service, self.material_service)),
            ("账号管理", AccountPage(self.account_service)),
            ("素材管理", MaterialPage(self.material_service)),
            ("下载中心", DownloadPage(self.download_service)),
            ("发布中心", PublishPage(self.material_service, self.account_service, self.publish_service)),
            ("系统设置", SettingsPage(self.settings_service, self.processing_service)),
            ("关于", AboutPage()),
        ]
        for title, page in pages:
            self.nav.addItem(QListWidgetItem(title))
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        sidebar_layout.addWidget(brand_block)
        sidebar_layout.addWidget(self.nav, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(sidebar)
        splitter.addWidget(self.stack)
        splitter.setSizes([148, 1172])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("就绪")

    def refresh_current_page(self):
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()
        elif hasattr(page, "load"):
            page.load()


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
