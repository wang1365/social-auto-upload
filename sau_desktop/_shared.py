"""Shared utilities, styles, and base widgets for sau_desktop."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QStyle, QStyleOptionButton
from PySide6.QtWidgets import (
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QHBoxLayout,
    QLabel,
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


class EventBus(QObject):
    """Cross-page communication bus for data change notifications."""
    accounts_changed = Signal()
    materials_changed = Signal()
    settings_changed = Signal()


class DebouncedSearch:
    """Debounce search input: only fires callback after user stops typing."""

    def __init__(self, line_edit: QLineEdit, callback, delay_ms: int = 300):
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(callback)
        line_edit.textChanged.connect(lambda: self._timer.start())


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


class _CheckableHeaderView(QHeaderView):
    """Horizontal header that draws a tri-state checkbox in the first column."""

    select_all_toggled = Signal(bool)  # True = check all, False = uncheck all

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._check_state = Qt.Unchecked
        self.setSectionsClickable(True)

    def checkState(self):
        return self._check_state

    def setCheckState(self, state):
        if self._check_state == state:
            return
        self._check_state = state
        self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex != 0:
            return
        option = QStyleOptionButton()
        option.rect = self._checkbox_rect(rect)
        option.state = QStyle.State_Enabled | QStyle.State_Active
        if self._check_state == Qt.Checked:
            option.state |= QStyle.State_On
        elif self._check_state == Qt.PartiallyChecked:
            option.state |= QStyle.State_NoChange
        else:
            option.state |= QStyle.State_Off
        self.style().drawControl(QStyle.CE_CheckBox, option, painter, self)

    def _checkbox_rect(self, section_rect):
        size = self.style().pixelMetric(QStyle.PM_IndicatorWidth, None, self)
        x = section_rect.x() + (section_rect.width() - size) // 2
        y = section_rect.y() + (section_rect.height() - size) // 2
        from PySide6.QtCore import QRect
        return QRect(x, y, size, size)

    def mousePressEvent(self, event):
        if self.logicalIndexAt(event.pos()) == 0:
            new_state = Qt.Unchecked if self._check_state == Qt.Checked else Qt.Checked
            self._check_state = new_state
            self.viewport().update()
            self.select_all_toggled.emit(new_state == Qt.Checked)
        else:
            super().mousePressEvent(event)


class DenseTable(QTableWidget):
    def __init__(self, headers: list[str], column_widths: list[int] | None = None):
        # 添加复选框列到表头
        headers_with_checkbox = [''] + headers
        super().__init__(0, len(headers_with_checkbox))
        self.column_widths = column_widths or []
        self.setHorizontalHeaderLabels(headers_with_checkbox)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.MultiSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(True)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(28)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setMinimumSectionSize(54)
        # 为复选框列设置固定宽度
        self.setColumnWidth(0, 40)
        for index, width in enumerate(self.column_widths):
            self.setColumnWidth(index + 1, width)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 替换默认 header 为带全选框的自定义 header
        self._header = _CheckableHeaderView(self)
        self.setHorizontalHeader(self._header)
        self._header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._header.select_all_toggled.connect(self._on_select_all)

        self._updating_checks = False
        self.itemChanged.connect(self._on_item_changed)

    def _on_select_all(self, checked: bool):
        self._updating_checks = True
        try:
            for row in range(self.rowCount()):
                item = self.item(row, 0)
                if item:
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        finally:
            self._updating_checks = False

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != 0 or self._updating_checks:
            return
        total = self.rowCount()
        if total == 0:
            self._header.setCheckState(Qt.Unchecked)
            return
        checked = sum(
            1 for r in range(total)
            if self.item(r, 0) and self.item(r, 0).checkState() == Qt.Checked
        )
        if checked == total:
            self._header.setCheckState(Qt.Checked)
        elif checked > 0:
            self._header.setCheckState(Qt.PartiallyChecked)
        else:
            self._header.setCheckState(Qt.Unchecked)

    def checked_rows(self) -> list[int]:
        """Return row indices where the checkbox is checked."""
        return [
            r for r in range(self.rowCount())
            if self.item(r, 0) and self.item(r, 0).checkState() == Qt.Checked
        ]

    def set_rows(self, rows: list[list[object]], payloads: list[object] | None = None):
        self._updating_checks = True
        self.setRowCount(len(rows))
        payloads = payloads or [None] * len(rows)
        for row_index, row in enumerate(rows):
            # 创建复选框项作为第一列
            check_item = QTableWidgetItem()
            check_item.setCheckState(Qt.Unchecked)
            check_item.setData(Qt.UserRole + 1, payloads[row_index])
            self.setItem(row_index, 0, check_item)
            
            # 设置其他列数据
            for column_index, value in enumerate(row):
                text = "" if value is None else str(value)
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, value)
                item.setData(Qt.UserRole + 1, payloads[row_index])
                item.setToolTip(text)
                self.setItem(row_index, column_index + 1, item)
        
        # 调整列宽，为复选框列预留空间
        self.setColumnWidth(0, 40)
        for index, width in enumerate(self.column_widths):
            self.setColumnWidth(index + 1, width)
        self._updating_checks = False
        # 重置全选框状态
        self._header.setCheckState(Qt.Unchecked)
    
    def get_payload(self, row: int) -> object:
        """Get the payload for a specific row"""
        if 0 <= row < self.rowCount():
            item = self.item(row, 0)  # 复选框列存储payload
            if item:
                return item.data(Qt.UserRole + 1)
        return None
