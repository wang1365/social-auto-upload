import { reactive } from "vue";
import type { components } from "./api-schema";

export type Task = components["schemas"]["Task"];
export type Account = components["schemas"]["Account"];
export type Material = components["schemas"]["Material"];
export type MaterialPage = components["schemas"]["MaterialPage"];
export type PublishItem = Omit<
  components["schemas"]["PublishItem"],
  "description" | "tags"
> & { description: string; tags: string[] };
export type Batch = components["schemas"]["BatchResult"];
export type TaskEvent = components["schemas"]["TaskEvent"];
export type BrowserState = components["schemas"]["BrowserState"];
export type BrowserAction = Pick<
  components["schemas"]["BrowserAction"],
  "kind"
> &
  Partial<Omit<components["schemas"]["BrowserAction"], "kind">>;
export const prefix = "/api/v2";
let token = "";
let authenticating: Promise<void> | null = null;
export const connection = reactive({
  online: true,
  streaming: false,
  error: "",
});

async function session() {
  if (!authenticating) {
    authenticating = (async () => {
      const response = await fetch(prefix + "/session", {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("无法连接本机服务");
      token = (await response.json()).token;
    })()
      .catch(() => {
        connection.online = false;
        connection.error = "无法连接本机服务，请确认启动窗口仍在运行";
        throw new Error(connection.error);
      })
      .finally(() => {
        authenticating = null;
      });
  }
  return authenticating;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  retried = false,
): Promise<T> {
  if (!token) await session();
  let response: Response;
  const headers = new Headers(options.headers);
  headers.set("X-SAU-Token", token);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  try {
    response = await fetch(prefix + path, {
      ...options,
      headers,
      credentials: "same-origin",
    });
    connection.online = true;
    connection.error = "";
  } catch {
    connection.online = false;
    connection.error = "本机服务连接已断开，请确认启动窗口仍在运行";
    throw new Error(connection.error);
  }
  if (response.status === 401 && !retried) {
    token = "";
    await session();
    return api(path, options, true);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.message || `请求失败（${response.status}）`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
export const media = (id: number, kind = "video") =>
  `${prefix}/materials/${id}/${kind}`;

export function upload(
  files: File[],
  onProgress: (percent: number) => void,
): Promise<Material[]> {
  return session().then(
    () =>
      new Promise((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", prefix + "/materials");
        request.setRequestHeader("X-SAU-Token", token);
        request.upload.onprogress = (event) => {
          if (event.lengthComputable)
            onProgress(Math.round((event.loaded / event.total) * 100));
        };
        request.onerror = () =>
          reject(new Error("导入中断，请检查本机服务后重试"));
        request.onload = () => {
          let data;
          try {
            data = JSON.parse(request.responseText);
          } catch {
            reject(new Error("导入失败，请重试"));
            return;
          }
          if (request.status >= 400)
            reject(new Error(data.message || "导入失败"));
          else resolve(data);
        };
        const form = new FormData();
        files.forEach((file) => form.append("files", file));
        request.send(form);
      }),
  );
}
