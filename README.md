# Polarscan

拍立得扫描件元数据管理系统。核心架构：

- 单一真值文件：数据目录中的 `_index.yaml`
- 分层结构：`core`（核心引擎）、`api`（公开接口）、`apps`（应用层）
- 标签以字符串存储，并由前缀区分语义（如 `char:电电Aki`、`event:xxx`）
- 缩略图缓存在独立的 `.thumbs/` 目录
- 原始 PNG 始终只读，程序不会修改图像内容

## 安装

```powershell
Set-Location D:\Dev\Workspace\Polarscan
python -m pip install -e .
```

依赖：PyYAML、Pillow、FastAPI、uvicorn、jinja2、python-multipart。

## 启动网页界面

```powershell
python -m apps.web.server
```

索引文件和缩略图默认写入项目根目录。浏览器打开 <http://127.0.0.1:8765>。

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
    server.py
    templates/
    static/

tests/                   # 隔离运行的核心与网页端测试
```

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

标签元数据保存在 `_index.yaml` 的 `tags` 字段中，界面按前缀选择对应的展示与编辑方式。

## 设计原则

- 程序只负责读写 YAML、生成缩略图、渲染界面和调用公开接口。
- 应用层只能通过 `polarscan.api.Polarscan` 修改数据，不能直接写入 YAML。
- 原始 PNG 只读，不改动任何字节。
- 根目录下划线开头的脚本用于一次性维护任务，默认不纳入 Git。
