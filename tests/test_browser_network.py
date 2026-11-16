import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.network import launch_browser_direct


def test_domestic_browser_disables_system_and_explicit_proxies_without_losing_options():
    browser = object()
    chromium = SimpleNamespace(launch=AsyncMock(return_value=browser))
    result = asyncio.run(launch_browser_direct(chromium,
        headless=True, channel="chrome", proxy={"server": "http://127.0.0.1:7890"},
        args=["--disable-blink-features=AutomationControlled", "--proxy-server=http://127.0.0.1:7890"]))
    assert result is browser
    chromium.launch.assert_awaited_once_with(headless=True, channel="chrome",
        args=["--disable-blink-features=AutomationControlled", "--no-proxy-server"])
