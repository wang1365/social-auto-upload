import type { components } from "./api-schema";

type BrowserCookie = components["schemas"]["BrowserCookie"];
interface HelperResponse {
  ok: boolean;
  error?: string;
  version?: number;
  cookies?: BrowserCookie[];
}

export class BrowserHelperUnavailable extends Error {}

function request(type: string, timeout: number): Promise<HelperResponse> {
  return new Promise((resolve, reject) => {
    const requestId = crypto.randomUUID();
    const origin = window.location.origin;
    const cleanup = () => {
      clearTimeout(timer);
      window.removeEventListener("message", receive);
    };
    const receive = (event: MessageEvent) => {
      if (
        event.source !== window ||
        event.origin !== origin ||
        event.data?.type !== "SAU_BROWSER_HELPER_RESPONSE" ||
        event.data.requestId !== requestId
      )
        return;
      cleanup();
      resolve(event.data);
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(
        type === "SAU_BROWSER_HELPER_PING"
          ? new BrowserHelperUnavailable("请先安装浏览器助手")
          : new Error("浏览器助手读取超时，请刷新页面后重试"),
      );
    }, timeout);
    window.addEventListener("message", receive);
    window.postMessage({ type, requestId }, origin);
  });
}

export async function importYouTubeCookiesFromBrowser(): Promise<
  BrowserCookie[]
> {
  const status = await request("SAU_BROWSER_HELPER_PING", 1500);
  if (!status.ok || status.version !== 1)
    throw new BrowserHelperUnavailable("请更新浏览器助手");
  const result = await request("SAU_BROWSER_HELPER_IMPORT", 10000);
  if (!result.ok || !Array.isArray(result.cookies))
    throw new Error(result.error || "无法读取当前浏览器的 YouTube 登录凭据");
  return result.cookies;
}
