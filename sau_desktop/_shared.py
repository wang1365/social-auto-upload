"""Shared utilities, styles, and base widgets for sau_desktop."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot, QSize, QRect
from PySide6.QtGui import QIcon, QFont, QColor, QPalette
from PySide6.QtWidgets import (
    QStyle,
    QStyleOptionButton,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QTextEdit,
    QCheckBox,
    QToolButton,
    QApplication,
)


# ============================================================
# Unified Color Scheme — Primary Blue (#2563eb)
# ============================================================
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
    border-bottom: 1px solid #e2e8f0;
    spacing: 6px;
    padding: 4px 8px;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #e2e8f0;
}
QWidget#Sidebar {
    background: #ffffff;
    border-right: 1px solid #e2e8f0;
}
QWidget#BrandBlock {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eff6ff, stop:1 #ffffff);
    border-bottom: 1px solid #e2e8f0;
}
QLabel#BrandTitle {
    font-size: 16px;
    font-weight: 800;
    color: #1e40af;
    letter-spacing: 1px;
    padding: 6px 10px;
}
QListWidget#Navigation {
    background: transparent;
    border: 0;
    padding: 8px 8px;
    outline: 0;
}
QListWidget#Navigation::item {
    min-height: 34px;
    padding: 6px 12px;
    border-radius: 6px;
    color: #475569;
    font-size: 13px;
}
QListWidget#Navigation::item:hover {
    background: #eff6ff;
    color: #1e40af;
}
QListWidget#Navigation::item:selected {
    background: #2563eb;
    color: #ffffff;
    border-left: 3px solid #1d4ed8;
    font-weight: 600;
}
QLabel#PageTitle {
    font-size: 20px;
    font-weight: 800;
    color: #1e293b;
}
QLabel#PageSubtitle {
    color: #64748b;
    font-size: 12px;
    margin-left: 8px;
}
QWidget#PageHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eff6ff, stop:1 #ffffff);
    border: 1px solid #bfdbfe;
    border-left: 4px solid #2563eb;
    border-radius: 8px;
}
/* KPI Card */
QFrame#KpiCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 4px;
}
QLabel#KpiIcon {
    font-size: 22px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    border-radius: 8px;
    qproperty-alignment: AlignCenter;
}
QLabel#KpiValue {
    font-size: 24px;
    font-weight: 800;
    color: #1e293b;
}
QLabel#KpiLabel {
    font-size: 12px;
    color: #64748b;
    font-weight: 500;
}
/* Selection bar */
QLabel#SelectionInfo {
    color: #475569;
    font-size: 12px;
    padding: 2px 8px;
    background: #f1f5f9;
    border-radius: 4px;
}
/* Status indicator */
QLabel#StatusDot {
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
    border-radius: 4px;
}
QLabel#StatusDot[status="ok"] { background: #22c55e; }
QLabel#StatusDot[status="error"] { background: #ef4444; }
QLabel#StatusDot[status="warning"] { background: #f59e0b; }
/* Collapsible section */
QFrame#CollapsibleSection {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-bottom: 6px;
}
QPushButton#CollapseToggle {
    background: transparent;
    border: none;
    text-align: left;
    padding: 4px 8px;
    font-weight: 700;
    font-size: 13px;
    color: #334155;
}
QPushButton#CollapseToggle:hover {
    background: #f8fafc;
    color: #2563eb;
}
QLabel#PreviewPlaceholder {
    background: #0f172a;
    color: #e5e7eb;
    border: 1px solid #1f2937;
    border-radius: 6px;
    padding: 10px;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    min-height: 28px;
    padding: 3px 8px;
    selection-background-color: #bfdbfe;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus-with-drop-down, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1.5px solid #2563eb;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    min-height: 28px;
    padding: 3px 14px;
    font-size: 12px;
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
QPushButton#PrimaryButton:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
}
QPushButton#DangerButton {
    color: #dc2626;
    border-color: #fecaca;
    background: #fef2f2;
}
QPushButton#DangerButton:hover {
    background: #fee2e2;
    border-color: #fca5a5;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    gridline-color: #f1f5f9;
    selection-background-color: #dbeafe;
    selection-color: #111827;
}
QHeaderView::section {
    background: #f1f5f9;
    color: #475569;
    border: 0;
    border-right: 1px solid #e2e8f0;
    border-bottom: 2px solid #e2e8f0;
    padding: 6px 8px;
    font-weight: 700;
    font-size: 12px;
}
QSplitter::handle {
    background: #e2e8f0;
}
QSplitter::handle:hover {
    background: #cbd5e1;
}
QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 12px 10px 12px;
    font-weight: 700;
    color: #1e293b;
    font-size: 13px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QProgressBar {
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    background: #f1f5f9;
    text-align: center;
    color: #475569;
    font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
    border-radius: 3px;
}
QScrollBar:vertical {
    background: #f1f5f9;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
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


class BackgroundCallbacks(QObject):
    def __init__(self, parent, thread, worker, on_done=None, on_error=None):
        super().__init__(parent)
        self._parent = parent
        self._thread = thread
        self._worker = worker
        self._on_done = on_done
        self._on_error = on_error

    @Slot(object)
    def done(self, result):
        try:
            if self._on_done:
                self._on_done(result)
        finally:
            self._cleanup()

    @Slot(str)
    def failed(self, message):
        try:
            if self._on_error:
                self._on_error(message)
            else:
                QMessageBox.critical(self._parent, "错误", message)
        finally:
            self._cleanup()

    def _cleanup(self):
        jobs = getattr(self._parent, "_background_jobs", None)
        if jobs is not None:
            jobs.discard(self)
        self._thread.quit()
        self._worker.deleteLater()
        self.deleteLater()


def run_background(parent, fn, on_done=None, on_error=None):
    thread = QThread(parent)
    worker = Worker(fn)
    callbacks = BackgroundCallbacks(parent, thread, worker, on_done, on_error)
    jobs = getattr(parent, "_background_jobs", None)
    if jobs is None:
        jobs = set()
        setattr(parent, "_background_jobs", jobs)
    jobs.add(callbacks)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(callbacks.done)
    worker.failed.connect(callbacks.failed)
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
    layout.setContentsMargins(14, 8, 14, 8)
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


# ============================================================
# KPI Card Widget (P1: Dashboard card-style statistics)
# ============================================================
KPICard_COLORS = [
    ("#eff6ff", "#3b82f6"),   # blue - accounts
    ("#f0fdf4", "#22c55e"),   # green - platforms
    ("#fefce8", "#eab308"),   # yellow - materials
    ("#fce7f3", "#ec4899"),   # pink - videos
]

KPICard_ICONS = ["\U0001f465", "\U0001f30d", "\U0001f4c4", "▶\ufe0f"]


def kpi_card(value: str, label: str, icon: str = "", color_index: int = 0) -> QFrame:
    """Create a styled KPI card with icon, large number, and label."""
    card = QFrame()
    card.setObjectName("KpiCard")
    bg_color, accent_color = KPICard_COLORS[color_index % len(KPICard_COLORS)]

    icon_label = QLabel(icon or KPICard_ICONS[color_index % len(KPICard_ICONS)])
    icon_label.setObjectName("KpiIcon")
    icon_label.setStyleSheet(f"""
        QLabel#KpiIcon {{
            background: {bg_color};
            color: {accent_color};
            border-radius: 8px;
        }}
    """)

    value_label = QLabel(value)
    value_label.setObjectName("KpiValue")

    label_label = QLabel(label)
    label_label.setObjectName("KpiLabel")

    info_layout = QVBoxLayout()
    info_layout.setSpacing(2)
    info_layout.addWidget(value_label)
    info_layout.addWidget(label_label)
    info_layout.addStretch()

    layout = QHBoxLayout(card)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(12)
    layout.addWidget(icon_label)
    layout.addLayout(info_layout, 1)
    return card


# ============================================================
# Status Dot Indicator (P2: Visual status indicator)
# ============================================================
def status_dot(status: str = "ok") -> QLabel:
    """Create a small colored dot for status indication.
    status: 'ok' (green), 'error' (red), 'warning' (yellow)
    """
    dot = QLabel()
    dot.setObjectName("StatusDot")
    dot.setProperty("status", status)
    dot.setStyle(dot.style())
    return dot


# ============================================================
# Collapsible Section (P1: Settings grouping / P2: Log area)
# ============================================================
class CollapsibleSection(QFrame):
    """A collapsible content section with a toggle header."""

    toggled = Signal(bool)  # True=expanded, False=collapsed

    def __init__(self, title: str, content_widget: QWidget, expanded: bool = True):
        super().__init__()
        self.setObjectName("CollapsibleSection")
        self._content = content_widget
        self._expanded = expanded

        self.toggle_btn = QPushButton(f"\u25BC {title}" if expanded else f"\u25B6 {title}")
        self.toggle_btn.setObjectName("CollapseToggle")
        self.toggle_btn.setCheckable(False)
        self.toggle_btn.clicked.connect(self._on_toggle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toggle_btn)
        layout.addWidget(self._content)
        self._update_visibility()

    def _on_toggle(self):
        self._expanded = not self._expanded
        self._update_visibility()
        self.toggled.emit(self._expanded)

    def _update_visibility(self):
        self._content.setVisible(self._expanded)
        arrow = "\u25BC" if self._expanded else "\u25B6"
        title = self.toggle_btn.text()
        # Replace leading arrow character
        if title.startswith("\u25BC"):
            title = title[2:]
        elif title.startswith("\u25B6"):
            title = title[2:]
        self.toggle_btn.setText(f"{arrow} {title}")

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._update_visibility()

    @property
    def is_expanded(self) -> bool:
        return self._expanded


# ============================================================
# Checkable Header View
# ============================================================
class _CheckableHeaderView(QHeaderView):
    """Horizontal header that draws a tri-state checkbox in the first column."""

    select_all_toggled = Signal(bool)

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
        return QRect(x, y, size, size)

    def mousePressEvent(self, event):
        if self.logicalIndexAt(event.pos()) == 0:
            new_state = Qt.Unchecked if self._check_state == Qt.Checked else Qt.Checked
            self._check_state = new_state
            self.viewport().update()
            self.select_all_toggled.emit(new_state == Qt.Checked)
        else:
            super().mousePressEvent(event)


# ============================================================
# Enhanced DenseTable (P0: hide IDs, P2: selection bar + better UX)
# ============================================================
class DenseTable(QTableWidget):
    """Enhanced table with checkboxes, selection counter, and tooltips."""

    selection_changed = Signal(int)  # checked_count

    def __init__(self, headers: list[str], column_widths: list[int] | None = None):
        headers_with_checkbox = [''] + headers
        super().__init__(0, len(headers_with_checkbox))
        self.column_widths = column_widths or []
        self.setHorizontalHeaderLabels(headers_with_checkbox)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(32)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setMinimumSectionSize(60)
        self.horizontalHeader().setHighlightSections(False)
        self.setColumnWidth(0, 38)
        for index, width in enumerate(self.column_widths):
            self.setColumnWidth(index + 1, width)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._header = _CheckableHeaderView(self)
        self.setHorizontalHeader(self._header)
        self._header.setDefaultAlignment(Qt.AlignLeft | AlignVCenter())
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
        self._emit_selection_count()

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != 0 or self._updating_checks:
            return
        total = self.rowCount()
        if total == 0:
            self._header.setCheckState(Qt.Unchecked)
            self.selection_changed.emit(0)
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
        self.selection_changed.emit(checked)

    def _emit_selection_count(self):
        checked = len(self.checked_rows())
        self.selection_changed.emit(checked)

    def checked_rows(self) -> list[int]:
        return [
            r for r in range(self.rowCount())
            if self.item(r, 0) and self.item(r, 0).checkState() == Qt.Checked
        ]

    def set_rows(self, rows: list[list[object]], payloads: list[object] | None = None):
        self._updating_checks = True
        self.setRowCount(len(rows))
        payloads = payloads or [None] * len(rows)
        for row_index, row in enumerate(rows):
            check_item = QTableWidgetItem()
            check_item.setCheckState(Qt.Unchecked)
            check_item.setData(Qt.UserRole + 1, payloads[row_index])
            self.setItem(row_index, 0, check_item)

            for column_index, value in enumerate(row):
                text = "" if value is None else str(value)
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, value)
                item.setData(Qt.UserRole + 1, payloads[row_index])
                item.setToolTip(text)
                self.setItem(row_index, column_index + 1, item)

        self.setColumnWidth(0, 38)
        for index, width in enumerate(self.column_widths):
            self.setColumnWidth(index + 1, width)
        self._updating_checks = False
        self._header.setCheckState(Qt.Unchecked)
        self.selection_changed.emit(0)

    def get_payload(self, row: int) -> object:
        if 0 <= row < self.rowCount():
            item = self.item(row, 0)
            if item:
                return item.data(Qt.UserRole + 1)
        return None


def AlignVCenter():
    return Qt.AlignVCenter
