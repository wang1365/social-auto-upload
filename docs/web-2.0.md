# 拾光分发 2.0

2.0 使用浏览器界面与本机 Python 服务。素材、SQLite 数据和账号登录凭据保存在此电脑，不上传到应用云端。关闭浏览器不会停止任务；关闭 Python 启动窗口会停止服务。

## 源码安装与启动

需要 Python 3.10–3.12、uv、Node.js 22.12+、Chrome，以及加入 PATH 的 FFmpeg/FFprobe。

```powershell
# 不覆盖已有 conf.py；首次安装时从示例复制
if (-not (Test-Path conf.py)) { Copy-Item conf.example.py conf.py }
powershell -ExecutionPolicy Bypass -File tools/build_web.ps1
uv run patchright install chromium
uv run playwright install chromium
```

构建完成后双击 `start-win.bat`，或执行：

```powershell
uv run sau-web
# 不自动打开浏览器
uv run sau-web --no-browser
# 自定义端口与独立数据目录
uv run sau-web --port 8766 --home D:\ShiguangData
```

默认地址为 `http://127.0.0.1:8765`，仅支持本机访问。已有同端口实例时打开已有界面；端口被其他程序占用时明确报错。

源码运行仍使用项目原有的 `db/`、`videoFile/`、`cookiesFile/`。分发 wheel 前必须先构建前端，`tools/build_web.ps1` 已包含前端和 Python wheel 构建；wheel 包含全部静态资源，安装包使用者无需 Node.js。

通过 wheel 安装后，Windows 默认将运行数据放在 `%LOCALAPPDATA%\Shiguang`，其他系统默认使用 `$XDG_DATA_HOME/Shiguang`（未设置时为 `~/.local/share/Shiguang`），可用 `--home` 或 `SAU_HOME` 指定已有数据目录。安装包只携带示例配置，不会打包构建电脑的本地 `conf.py`。

## 界面使用

- **工作台**：查看近期任务、需要登录的账号和快捷入口。
- **素材库**：拖入或选择视频，搜索、筛选、预览，批量选择后进入发布。
- **发布中心**：选择素材和账号，为每条素材编辑标题、正文及话题；支持批量填充。每条视频分别发布到所有选中账号，确认对话框会显示总任务数。
- **下载中心**：创建单条 YouTube 下载，查看字幕和后续处理任务。历史素材仍可预览，但不会补造旧日志。
- **YouTube 浏览**：启动本机 Chrome 浏览会话，在系统内浏览完整站点、搜索、访问频道和点击视频。支持中文输入与粘贴。打开视频后可直接下载，或编辑标题、正文、话题并选择多个已登录账号，确认后下载并自动排队分发。下载失败不会创建发布任务；重复提交不会重复分发。任务详情可查看各平台的后续发布状态。
- **账号管理**：扫码登录、检查状态、修改名称、导入导出登录凭据。如果扫码流程受验证阻碍，可在原任务结束后使用“打开浏览器登录”。
- **设置**：配置下载代理、YouTube Netscape Cookie、处理参数和话题模板。高级处理参数默认折叠。

视频号不单独提交正文描述。首版 Web 只提供立即发布视频；B站、图文和原有定时能力继续通过已有 CLI/底层入口使用，不在此版本扩展 UI。

YouTube 网页画面和交互显示在系统内；需要声音时可点击“独立窗口播放”，使用同一个浏览会话在 Chrome 窗口播放。YouTube 登录资料仅保存在本机的 `runtime/youtube-browser/`，浏览器关闭后仍保留。下载使用设置中导入的 Netscape Cookie；网页登录与下载 Cookie 独立管理。自动分发使用下载完成的原视频，独立的视频处理任务仍可继续运行。

设置中的 YouTube 代理只用于 YouTube 浏览和下载。抖音、小红书、快手、视频号的登录、状态校验和上传均显式禁用浏览器代理，不继承 Windows 系统代理。该设置无法绕过 VPN/TUN 等系统网络层转发，也不能保证平台接受当前出口 IP。小红书返回 `300012` 时，页面会显示平台的网络风险提示，可切换可靠网络或使用“打开浏览器登录”查看。

原视频由本机接口读取并支持拖动播放。浏览器无法解码时，可在预览弹窗生成兼容版本；原文件保留，兼容预览缓存在 `runtime/previews/`。

## 从 1.0 升级

先停止旧客户端，保留运行数据，再构建启动 2.0。服务首次启动会通过 SQLite backup API 备份数据库至 `db/database.pre-v2.<随机标识>.db`，随后执行可重复运行的增量迁移。不要删除数据库或运行旧文档中的“删除重建”步骤。

账号和素材 ID 保留，原配置及 Cookie 继续使用。CLI 的 `cookies/` 与 Web 的 `cookiesFile/` 暂不合并，可通过账号凭据导入导出迁移。Web 不自动发现 CLI 账号。

2.0 移除了 `sau-desktop`、PySide6 和 mpv。`sau_backend.py` 改为启动 Web 服务，旧 Flask 路由不再兼容。

需要回退时：停止 2.0，保留一份当前数据库及文件，切回 1.0，并用升级前的数据库备份替换 `db/database.db`。必须在所有进程退出后恢复，并移走旧的 `database.db-wal`、`database.db-shm`。数据库备份不包含视频文件；需要完整回退时同时备份运行目录。

## 任务行为

- 状态和日志保存在 SQLite，SSE 用递增事件 ID 断线续接；推送不可用时页面定时查询。
- 发布串行执行；同一账号的登录、检查与发布互斥。下载最多并发 2 个，处理并发取设置值。
- 同一提交标识创建同一个批次，避免连续点击重复排队。重试链已有成功或待核实结果时拒绝重复重试。
- 待执行任务可取消。执行中的任务不能强制取消，也不能删除其正在使用的素材或账号。
- 重启后待执行任务继续排队；执行中的下载、处理等标记为中断，发布标记为“结果待核实”。已有平台成功回执的发布保留成功状态。
- 发布尝试前失败可重试；提交后未获得确认时，先到平台核实，不自动重发。成功仅指平台已确认提交，不代表通过平台后续审核。
- 删除任务记录不删除素材或平台内容；删除素材则删除对应视频和字幕文件。

## 开发与验证

```powershell
uv sync --extra dev
uv run python tools/export_web_api.py
npm.cmd --prefix sau_frontend ci
npm.cmd --prefix sau_frontend run api:types
npm.cmd --prefix sau_frontend run build
uv run pytest -q
npm.cmd --prefix sau_frontend test
```

开发时可分别启动 `uv run sau-web --no-browser` 和 `npm.cmd --prefix sau_frontend run dev`。Vite 代理 `/api` 到本机 8765 端口。

Python 代码位于 `sau_web/`，前端位于 `sau_frontend/`，核心媒体与平台能力位于 `sau_core/`、`uploader/`。接口统一使用 `/api/v2`，前端类型从 OpenAPI 生成。构建产物不入库，由构建脚本生成后打入 wheel。

自动化验证使用临时运行目录和模拟平台，不使用真实账号，不发布真实内容。真实四平台扫码、人工验证、平台改版及实际视频发布需要单独联调。
