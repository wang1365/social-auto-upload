"""Account-owned Chrome profiles; credentials stay inside the local runtime."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from utils.network import launch_browser_direct, launch_persistent_browser_direct

_logger = logging.getLogger(__name__)
_IMPORT_STATE = ".sau-credentials.json"
_SESSION_STATE = ".sau-session-cookies.json"


class ProfileInUse(RuntimeError):
    pass


def account_profile_dir(account_file):
    cookie = Path(account_file).resolve()
    key = hashlib.sha256(os.path.normcase(cookie.name).encode()).hexdigest()[:24]
    return cookie.parent.parent / "runtime" / "douyin-browser" / key


@contextmanager
def profile_lock(profile_dir):
    profile = Path(profile_dir)
    profile.parent.mkdir(parents=True, exist_ok=True)
    with profile.with_suffix(".lock").open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ProfileInUse("此抖音账号的浏览器资料正在使用，请结束该账号的其他任务后重试") from None
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _fingerprint(account_file):
    path = Path(account_file)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


async def save_douyin_storage(context, account_file, profile_dir=None, *, reset_bootstrap=False):
    _write_json(account_file, await context.storage_state())
    if profile_dir is not None:
        marker = Path(profile_dir) / _IMPORT_STATE
        metadata = {} if reset_bootstrap else _read_json(marker)
        _write_json(marker, {**metadata, "credentials_sha256": _fingerprint(account_file)})


def remove_account_profile(account_file):
    profile = account_profile_dir(account_file)
    # Refuse redirected paths; only this account's managed directory is owned.
    if profile.resolve().parent != profile.parent.resolve():
        raise RuntimeError("账号浏览器资料路径异常，未删除")
    with profile_lock(profile):
        if profile.exists():
            shutil.rmtree(profile)


async def _restore_credentials(context, account_file, profile):
    fingerprint = _fingerprint(account_file)
    metadata = _read_json(profile / _IMPORT_STATE)
    if fingerprint and metadata.get("credentials_sha256") != fingerprint:
        state = json.loads(Path(account_file).read_text(encoding="utf-8"))
        if (not isinstance(state, dict) or not isinstance(state.get("cookies"), list)
                or not isinstance(state.get("origins", []), list)):
            raise ValueError("抖音登录凭据格式无效，请重新导入或登录")
        await context.clear_cookies()
        await context.add_cookies(state["cookies"])
        metadata = {"credentials_sha256": fingerprint, "bootstrap_fingerprint": fingerprint,
                    "origins": state.get("origins", [])}
        _write_json(profile / _IMPORT_STATE, metadata)
    else:
        saved = _read_json(profile / _SESSION_STATE)
        if saved.get("credentials_sha256") == fingerprint and saved.get("cookies"):
            # Chrome may discard session cookies on a clean exit even when its
            # other cookies, localStorage and IndexedDB live in a profile.
            await context.add_cookies(saved["cookies"])
    # Keep bootstrap data available for origins not visited on the first run.
    # The marker prevents later visits from replacing learned device state.
    if metadata.get("origins"):
        await context.add_init_script("""(() => {
            const origins = """ + json.dumps(metadata["origins"]) + "; const fingerprint = " + json.dumps(metadata["bootstrap_fingerprint"]) + """;
            const entry = origins.find(item => item.origin === location.origin);
            if (!entry || localStorage.getItem('__sau_credentials_import') === fingerprint) return;
            localStorage.clear();
            for (const item of entry.localStorage || []) localStorage.setItem(item.name, item.value);
            localStorage.setItem('__sau_credentials_import', fingerprint);
        })();""")


@asynccontextmanager
async def open_douyin_browser(
    playwright, account_file, *, profile_dir=None, headless=True,
    bypass_csp=False, load_credentials=True,
):
    options = {"bypass_csp": bypass_csp}
    if bypass_csp:
        options["permissions"] = ["geolocation"]
    if profile_dir is None:
        browser = await launch_browser_direct(playwright.chromium, headless=headless, channel="chrome")
        context = None
        try:
            context = await browser.new_context(
                **options, storage_state=str(account_file) if load_credentials and Path(account_file).is_file() else None,
            )
            yield context
        finally:
            try:
                if context:
                    await context.close()
            finally:
                await browser.close()
        return

    profile = Path(profile_dir)
    with profile_lock(profile):
        profile.mkdir(parents=True, exist_ok=True)
        context = await launch_persistent_browser_direct(
            playwright.chromium, str(profile), headless=headless, channel="chrome", **options,
        )
        try:
            if load_credentials:
                await _restore_credentials(context, account_file, profile)
            yield context
        finally:
            try:
                cookies = [item for item in await context.cookies() if item.get("expires", -1) < 0]
                _write_json(profile / _SESSION_STATE, {
                    "credentials_sha256": _fingerprint(account_file), "cookies": cookies,
                })
            except Exception:
                _logger.warning("抖音浏览器会话未能保存，将在下次打开时检查登录状态")
            finally:
                await context.close()
