/* Reads through the browser's own API; never decrypts browser database files. */
function allowedSender(sender) {
  try {
    const url = new URL(sender.url);
    return (
      url.protocol === "http:" &&
      ["127.0.0.1", "localhost"].includes(url.hostname) &&
      url.pathname === "/settings" &&
      Number.isInteger(sender.tab?.id)
    );
  } catch {
    return false;
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "SAU_READ_YOUTUBE_COOKIES") return;
  if (!allowedSender(sender)) {
    sendResponse({ ok: false, error: "请从本机拾光分发的设置页面导入" });
    return;
  }
  (async () => {
    const stores = await chrome.cookies.getAllCookieStores();
    const storeId = stores.find((store) =>
      store.tabIds.includes(sender.tab.id),
    )?.id;
    if (!storeId) throw new Error("store unavailable");
    const groups = await Promise.all(
      ["youtube.com", "google.com"].map((domain) =>
        chrome.cookies.getAll({ domain, storeId }),
      ),
    );
    const cookies = groups
      .flat()
      .filter((cookie) => {
        const host = cookie.domain.replace(/^\./, "").toLowerCase();
        return (
          ["youtube.com", "google.com"].some(
            (root) => host === root || host.endsWith("." + root),
          ) &&
          !cookie.partitionKey &&
          (cookie.session || cookie.expirationDate > Date.now() / 1000)
        );
      })
      .map((cookie) => ({
        name: cookie.name,
        value: cookie.value,
        domain: cookie.domain,
        path: cookie.path,
        secure: cookie.secure,
        httpOnly: cookie.httpOnly,
        expires: cookie.session ? null : cookie.expirationDate,
      }));
    sendResponse({ ok: true, cookies });
  })().catch(() =>
    sendResponse({
      ok: false,
      error:
        "无法读取当前浏览器的登录凭据，请确认助手有 YouTube 和 Google 的访问权限",
    }),
  );
  return true;
});
