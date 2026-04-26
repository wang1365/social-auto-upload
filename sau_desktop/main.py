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
from sau_desktop._shared import APP_STYLE
from sau_desktop.about_page import AboutPage
from sau_desktop.account_page import AccountLoginDialog, AccountPage
from sau_desktop.dashboard_page import DashboardPage
from sau_desktop.download_page import (
    CreateDownloadDialog,
    DownloadPage,
    DownloadTaskDetailDialog,
)
from sau_desktop.material_page import MaterialPage
from sau_desktop.publish_page import PublishPage
from sau_desktop.settings_page import SettingsPage

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
