"""Validate and serialize credentials explicitly imported from a browser."""

import time


LOGIN_COOKIE_NAMES = {
    "SID", "HSID", "SSID", "APISID", "SAPISID", "LOGIN_INFO",
    "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PAPISID", "__Secure-3PAPISID",
}


def is_youtube_cookie_domain(domain):
    host = domain.lstrip(".").lower()
    return any(
        host == root or host.endswith("." + root)
        for root in ("youtube.com", "google.com")
    )


def browser_cookies_to_netscape(cookies):
    rows = ["# Netscape HTTP Cookie File", "# Imported from the current browser"]
    has_login = False
    for cookie in cookies:
        if not is_youtube_cookie_domain(cookie.domain):
            continue
        fields = (cookie.domain, cookie.path, cookie.name, cookie.value)
        if (
            any(any(char in field for char in "\r\n\t\0") for field in fields)
            or not cookie.path.startswith("/")
        ):
            raise ValueError("浏览器凭据格式无效，请重新导入")
        if cookie.expires is not None and 0 < cookie.expires <= time.time():
            continue
        domain = cookie.domain.lower()
        expiry = int(cookie.expires) if cookie.expires and cookie.expires > 0 else 0
        rows.append("\t".join((
            ("#HttpOnly_" if cookie.httpOnly else "") + domain,
            "TRUE" if domain.startswith(".") else "FALSE",
            cookie.path, "TRUE" if cookie.secure else "FALSE",
            str(expiry), cookie.name, cookie.value,
        )))
        has_login |= cookie.name in LOGIN_COOKIE_NAMES and bool(cookie.value)
    if not has_login:
        raise ValueError("当前浏览器中未找到有效的 YouTube 登录凭据，请先在同一浏览器登录 YouTube 再导入")
    return ("\n".join(rows) + "\n").encode("utf-8")
