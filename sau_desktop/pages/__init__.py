"""All menu page widgets."""

from sau_desktop.pages.about_page import AboutPage
from sau_desktop.pages.account_page import AccountLoginDialog, AccountPage
from sau_desktop.pages.dashboard_page import DashboardPage
from sau_desktop.pages.download_page import (
    CreateDownloadDialog,
    DownloadPage,
    DownloadTaskDetailDialog,
)
from sau_desktop.pages.material_page import MaterialPage
from sau_desktop.pages.publish_page import PublishPage
from sau_desktop.pages.settings_page import SettingsPage

__all__ = [
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
