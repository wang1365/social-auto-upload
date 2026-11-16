from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser


def probe(url):
    try:
        with urllib.request.urlopen(url + "/api/v2/health", timeout=1) as response:
            return json.load(response).get("application") == "social-auto-upload"
    except (OSError, ValueError):
        return False


def main(argv=None):
    raw_args = sys.argv[1:] if argv is None else argv
    if len(raw_args) == 3 and raw_args[0] == "--worker":
        from sau_web.worker import Worker

        Worker(raw_args[1], raw_args[2]).run()
        return 0
    parser = argparse.ArgumentParser(description="拾光分发 2.0 本机 Web 服务")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--home", help="运行数据目录；源码默认项目目录，安装包默认用户数据目录"
    )
    args = parser.parse_args(raw_args)
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 至 65535 之间")
    if args.home:
        os.environ["SAU_HOME"] = os.path.abspath(args.home)
    url = f"http://127.0.0.1:{args.port}"
    if probe(url):
        print(f"服务已运行：{url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", args.port))
        except OSError:
            print(
                f"端口 {args.port} 已被其他程序占用，请使用 --port 指定其他端口。",
                file=sys.stderr,
            )
            return 1
    from sau_web.app import create_app
    import uvicorn

    app = create_app()

    def open_when_ready():
        for _ in range(60):
            if probe(url):
                webbrowser.open(url)
                return
            time.sleep(0.5)

    if not args.no_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    print(f"拾光分发 2.0：{url}（保持此进程运行，浏览器关闭后任务继续执行）")
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
