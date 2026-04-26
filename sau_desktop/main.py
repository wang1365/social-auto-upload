"""Desktop client entry point: MainWindow and application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sau_core.services import (
    AccountService,
    DownloadService,
    MaterialService,
    ProcessingService,
    PublishService,
    SettingsService,
    ensure_runtime_schema,
)
from sau_desktop._shared import APP_STYLE, EventBus
from sau_desktop.pages import (
    AboutPage,
    AccountLoginDialog,
    AccountPage,
    CreateDownloadDialog,
    DashboardPage,
    DownloadPage,
    DownloadTaskDetailDialog,
    MaterialPage,
    PublishPage,
    SettingsPage,
)

# Re-export for backward compatibility (tests import from sau_desktop.main)
__all__ = [
    "main",
    "MainWindow",
    "DashboardPage",
    "AccountPage",
    "AccountLoginDialog",
    "MaterialPage",
    "DownloadPage",
    "CreateDownloadDialog",
    "DownloadTaskDetailDialog",
    "PublishPage",
    "SettingsPage",
    "AboutPage",
]


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
        self.event_bus = EventBus()

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
            ("仪表盘", DashboardPage(self.account_service, self.material_service, self.event_bus)),
            ("账号管理", AccountPage(self.account_service, self.event_bus)),
            ("素材管理", MaterialPage(self.material_service, self.event_bus)),
            ("下载中心", DownloadPage(self.download_service, self.event_bus)),
            ("发布中心", PublishPage(self.material_service, self.account_service, self.publish_service, self.event_bus)),
            ("系统设置", SettingsPage(self.settings_service, self.processing_service, self.event_bus)),
            ("关于", AboutPage()),
        ]
        for title, page in pages:
            self.nav.addItem(QListWidgetItem(title))
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.nav.setCurrentRow(0)
        sidebar_layout.addWidget(brand_block)
        sidebar_layout.addWidget(self.nav, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(sidebar)
        splitter.addWidget(self.stack)
        splitter.setSizes([148, 1172])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("就绪")

    def _on_nav_changed(self, index):
        # Check for unsaved changes on current page before switching
        current = self.stack.currentWidget()
        if hasattr(current, "check_unsaved") and not current.check_unsaved():
            # User chose not to leave, revert navigation
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(self.stack.currentIndex())
            self.nav.blockSignals(False)
            return
        self.stack.setCurrentIndex(index)
        page = self.stack.widget(index)
        if hasattr(page, "refresh"):
            page.refresh()
        elif hasattr(page, "load"):
            page.load()

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
