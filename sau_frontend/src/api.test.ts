import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("本机会话与请求", () => {
  it("首次连接失败时显示服务离线，允许后续重连", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const { api, connection } = await import("./api");
    await expect(api("/accounts")).rejects.toThrow("无法连接本机服务");
    expect(connection.online).toBe(false);
  });
  it("并行加载页面时只建立一次会话，并给写请求添加令牌", async () => {
    const fetch = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/session"))
        return new Response(JSON.stringify({ token: "test-token" }));
      expect(new Headers(options?.headers).get("X-SAU-Token")).toBe(
        "test-token",
      );
      return new Response(JSON.stringify([]));
    });
    vi.stubGlobal("fetch", fetch);
    const { api, post } = await import("./api");
    await Promise.all([
      api("/accounts"),
      api("/tasks"),
      post("/downloads", { url: "url" }),
    ]);
    expect(
      fetch.mock.calls.filter(([url]) => url.endsWith("/session")),
    ).toHaveLength(1);
  });
  it("会话重建后保留发布幂等标识，不改写请求内容", async () => {
    let session = 0,
      requests = 0;
    const bodies: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options?: RequestInit) => {
        if (url.endsWith("/session"))
          return new Response(JSON.stringify({ token: `token-${++session}` }));
        bodies.push(String(options?.body));
        requests++;
        return requests === 1
          ? new Response("{}", { status: 401 })
          : new Response('{"id":"same-batch"}');
      }),
    );
    const { post } = await import("./api");
    await expect(
      post("/publish-batches", { request_key: "stable-request" }),
    ).resolves.toEqual({ id: "same-batch" });
    expect(session).toBe(2);
    expect(bodies).toEqual([
      '{"request_key":"stable-request"}',
      '{"request_key":"stable-request"}',
    ]);
  });
});
