# social-auto-upload for Codex

## 项目概览

`social-auto-upload` 是一个多平台视频自动发布工具，支持一键上传、定时发布、账号管理等能力。

支持平台包括：`Douyin`、`Bilibili`、`Xiaohongshu`、`Kuaishou`、`WeChat Channel`、`Baijiahao`、`TikTok`。

项目由 Python 后端 + Vue 前端组成，并提供命令行入口。

## 技术栈

### 后端

- Framework: `Flask`
- 自动化: `playwright`
- 数据库: `SQLite`（`db/database.db`）
- 通信: REST API + 登录流程 SSE

### 前端

- Framework: `Vue.js`
- Build: `Vite`
- UI: `Element Plus`
- State: `Pinia`
- Router: `Vue Router`

### CLI

优先使用新入口：`sau douyin ...`（不要优先依赖旧 example 脚本）。

## 快速启动

### 后端

```bash
pip install -r requirements.txt
playwright install chromium
python db/createTable.py
python sau_backend.py
```

后端默认地址：`http://localhost:5409`

### 前端

```bash
cd sau_frontend
npm install
npm run dev
```

前端默认地址：`http://localhost:5173`

## CLI 常用命令

```bash
sau douyin login --account <account_name>
sau douyin check --account <account_name>
sau douyin upload --account <account_name> --file <video_file> --title <title> [--tags tag1,tag2] [--schedule YYYY-MM-DD HH:MM]
```

安装内置 skill：

```bash
sau skill install
```

## 代码组织

- 后端主要位于仓库根目录、`myUtils/`、`uploader/`
- 前端位于 `sau_frontend/`
- 数据库文件：`db/database.db`
- 配置模板：`conf.example.py`（复制为 `conf.py` 后按需配置）
- Python 依赖：`requirements.txt`
- 前端依赖：`sau_frontend/package.json`

## Codex 工作约定

- 修改代码时优先保持最小变更，避免无关重构。
- 搜索优先使用 `rg` / `rg --files`。
- 若仓库存在未提交改动，不回滚与当前任务无关的改动。
- 涉及 CLI 能力时，默认优先使用 `sau douyin ...` 路径验证行为。

