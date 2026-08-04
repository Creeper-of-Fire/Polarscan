# Polarscan

拍立得扫描件元数据管理系统。核心架构：

- 单一真值文件：数据目录中的 `_index.yaml`
- 分层结构：`polarscan`（核心引擎）、`apps`（应用层）
- 标签以字符串存储，并由前缀区分语义（如 `char:电电Aki`、`event:xxx`）
- 缩略图缓存在独立的 `.thumbs/` 目录
- 原始 PNG 始终只读，程序不会修改图像内容

## 技术栈

- **后端**：Python 3.10+ / FastAPI / `polarscan.api` 公共接口
- **前端**：Vue 3 (Composition API + `<script setup>`) / TypeScript / Pinia / Vue Router / Vite / Naive UI / VueUse
- **构建**：pnpm workspace（`frontend/` 子包）

## 安装

```powershell
# 后端（开发模式安装）
Set-Location D:\Dev\Workspace\Polarscan
python -m pip install -e .

# 前端依赖（首次或 lockfile 变化时）
pnpm install
```

后端依赖：PyYAML、Pillow、FastAPI、uvicorn、python-multipart。
前端依赖：pnpm 自动解析 `frontend/package.json`。

## 启动

### 生产模式（推荐）

```powershell
# 1. 构建前端
pnpm build

# 2. 启动后端 (同时服务 SPA + JSON API)
python -m apps.web.server
```

浏览器打开 <http://127.0.0.1:8765>。

### 开发模式（前端热更新）

```powershell
pnpm dev
```

concurrently 同时启动：

- **Vite** dev server：<http://127.0.0.1:5173>（前端 HMR）
- **FastAPI**：<http://127.0.0.1:8765>（JSON API + 静态资源）

Vite 把 `/api`、`/thumb`、`/img`、`/pool` 等路径代理到 FastAPI。

## 项目结构

```text
polarscan/
  core/                  # 核心引擎
    index.py             # Polaroid、Asset 数据模型与标签辅助函数
    storage.py           # _index.yaml 读写
    asset_thumb.py       # 资产哈希与缩略图生成
    id_gen.py            # 拍立得 id 派生
  api.py                 # 公开 Python 接口，应用层必须经由这里访问

apps/
  web/                   # FastAPI 本地网页界面
    server.py            # 路由 + SPA 静态挂载 + catch-all
    static/              # 仅保留 path-parse.js (测试仍引用)
    library_resolver.py  # drop 工作流 F:盘路径识别

frontend/                # Vue SPA (pnpm 子包)
  src/
    views/               # ListView / NewView / BenchView / PoolIndexView / PoolEditView
    components/          # AppShell / AssetModal
    stores/              # Pinia: polarscan (全表缓存 + 当前选中)
    composables/         # useAutosave / useDropzone / useChipStream / usePathParse
    api/                 # fetch 封装 + 按域分组的端点
    router/              # Vue Router 表
  vite.config.ts         # proxy /api /thumb /img /pool 等到 :8765
  package.json

tests/                   # 隔离运行的核心与端到端测试
```

## JSON API（Vue SPA 使用）

| Method | 路径 | 说明 |
|--------|------|------|
| GET | `/api/polaroids[?tag=X]` | 全表或按 tag 过滤 |
| GET | `/api/polaroids/{pid}` | 单个 polaroid 详情 |
| GET | `/api/polaroids/{pid}/goto/{prev\|next\|untagged}` | 跳转目标 |
| GET | `/api/all-tags[?prefix=X]` | 已用 tag values |
| GET | `/api/pool/{prefix}` | 标签池 |
| GET | `/api/pool/{prefix}/{key}` | 单个标签详情 |
| GET | `/api/suggest-id?shot_date=X&primary_char=Y` | 派生 id |
| POST | `/bench/{pid}/autosave` (form) | 自动保存 tags / shot_date / notes |
| POST | `/bench/{pid}/save-assets` (JSON) | 替换 assets 列表 |
| POST | `/bench/{pid}/delete` (form) | 删除 polaroid |
| POST | `/new` (form) | 创建 polaroid |
| POST | `/pool/{prefix}/{key}/edit` (form) | 保存标签 |
| POST | `/pool/{prefix}/{key}/delete` (form) | 删除标签 |
| POST | `/reload` (form) | 从磁盘重载索引 |
| POST | `/api/drop/identify` (JSON) | drop 工作流识别 |
| POST | `/api/polaroids/{pid}/append-files` (JSON) | 追加资产 |

GET 路由 `/`、`/list`、`/new`、`/bench/{pid}`、`/pool/{prefix}`、`/pool/{prefix}/{key}/edit` 一律返回 SPA `index.html`，由 Vue Router 接管前端路由。

资源路径：

| Method | 路径 | 说明 |
|--------|------|------|
| GET | `/thumb/{pid}[/{asset_idx}]` | 缩略图 |
| GET | `/img/{pid}[/{asset_idx}]` | 原图（仅主动访问时读 F 盘）|

## 标签前缀约定

| 前缀 | 含义 |
|---|---|
| `char` | 角色（含真人） |
| `event` | 有明确日期的活动 |
| `theme` | 跨日期主题 |
| `moment` | 轻量的一次性时刻 |
| `collection` | 跨事件系列 |
| `composite` | 多张拍立得的组合展示 |
| `shot` | 构图类型（`solo`、`pair`、`group`） |
| `sig` | 签名状态 |

## 设计原则

- 程序只负责读写 YAML、生成缩略图、渲染界面和调用公开接口。
- 应用层只能通过 `polarscan.api.Polarscan` 修改数据，不能直接写入 YAML。
- 原始 PNG 只读，不改动任何字节。
- 根目录下划线开头的脚本用于一次性维护任务，默认不纳入 Git。

## 迁移记录

2026-08：从 Jinja2 + Alpine.js + 原生 JS/CSS 迁移到 Vue 3 + Naive UI + Pinia + Vite + pnpm workspace。

- 删除：`apps/web/templates/`（6 个 Jinja2 模板）、`apps/web/static/drop.js` / `assets-modal.js` / `app.css`
- 新增：`frontend/`（Vue SPA + Vite 构建）、`apps/web/server.py` 改造（保留所有 POST，新增 JSON API，挂载 SPA catch-all）
- CDN 全部去除：Alpine.js、hash-wasm、blake2b 全部由 pnpm 安装
- localStorage 跨页通信 → Pinia store + 后端 JSON API