(() => {
  const origin = window.location.origin;
  window.addEventListener("message", (event) => {
    if (event.source !== window || event.origin !== origin) return;
    const message = event.data;
    if (
      !message ||
      typeof message.requestId !== "string" ||
      !/^[a-f0-9-]{36}$/.test(message.requestId)
    )
      return;
    const reply = (payload) =>
      window.postMessage(
        {
          type: "SAU_BROWSER_HELPER_RESPONSE",
          requestId: message.requestId,
          ...payload,
        },
        origin,
      );
    if (message.type === "SAU_BROWSER_HELPER_PING") {
      reply({ ok: true, version: 1 });
      return;
    }
    if (message.type !== "SAU_BROWSER_HELPER_IMPORT") return;
    if (
      window.location.pathname !== "/settings" ||
      !navigator.userActivation?.isActive
    ) {
      reply({ ok: false, error: "请在设置页面点击导入按钮" });
      return;
    }
    chrome.runtime.sendMessage(
      { type: "SAU_READ_YOUTUBE_COOKIES" },
      (response) => {
        if (chrome.runtime.lastError || !response) {
          reply({ ok: false, error: "浏览器助手连接中断，请刷新页面后重试" });
          return;
        }
        reply(response);
      },
    );
  });
})();
