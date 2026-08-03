# Polarscan

拍立得扫描件的元数据管理系统。核心架构：

- 单文件真值层 `_index.yaml`（在数据目录）
- 多工具分层：`core`（引擎）/ `api`（接口）/ `apps`（wrapper）
- tag = 字符串，前缀驱动多态（`char:strawberry`, `event:xxx` 等）
- 缩略图缓存独立目录 `.thumbs/`
- 原 PNG 只读，软件不越界改图

## 安装

```bash
cd D:\Dev\Workspace\Polarscan
pip install -e .
```

依赖：PyYAML, Pillow, FastAPI, uvicorn, jinja2, python-multipart。

## 启动 Web 前端

```bash
# 数据路径在 server.py 里改 LIBRARY_ROOT
python -m apps.web.server
```

浏览器打开 http://127.0.0.1:8765

## 项目结构

```
polarscan/
  core/            # 引擎 (load/save/thumb/path)
    index.py       # Polaroid / Asset dataclass
    storage.py     # _index.yaml 读写
    thumb.py       # 缩略图生成 + 缓存
    resolver.py    # asset 路径解析
  api.py           # Python API（apps 必须走这里）

apps/
  web/             # FastAPI 本地 web 前端
    server.py
    templates/
    static/
```

## tag 约定

| prefix  | 语义              |
|---------|-------------------|
| char    | 角色 (含真人)     |
| event   | 有具体日期的活动  |
| theme   | 跨日期主题        |
| moment  | 轻量 / 一次性 moment |
| collection | 跨事件系列       |
| composite | 多 polaroid 联合呈现 |
| shot    | solo/pair/group   |
| sig     | signature 状态     |

约定写在 `config`，display 按 prefix 多态路由。

## 设计原则

- 软件只做：读 yaml / 生成 thumb / 渲染前端 / 写回 yaml。
- 原 PNG 只读，不动一字节。
- 复杂任务 agent 干，不塞给软件。
