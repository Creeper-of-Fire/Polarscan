# AGENTS.md — Polarscan

> 本文件是项目的**演进导航**，不是现状描述。
>
> - 现状（项目结构 / 安装 / 启动 / API / 标签语义）→ `README.md`
> - 行为真值 → `polarscan/` 与 `apps/` 的源码
> - 设计不变量 + 状态 → `docs/spec/` 各 spec（按主题分散，索引见 `docs/spec/README.md`）
> - 派生数据与一次性脚本 → `.gitignore`
>
> 本文件承担 **README 与代码都不会承担的职责**：
>
> 1. **core 的设计意图**——为什么这么分
> 2. **已否决的设计**——历史决策记录（spec 是当下真相，否决历史留这里）
>
> 这两段都是**未来导向**——给下一次重构 / 加字段 / 改 schema 的 agent 看。
> 已完成的事在 commit message；待办的事在 issue tracker；不在这里。

## 一、Core 的设计意图

### 角色：无知即力量

core 是 Polarscan 的算法 + schema 真相源。它的"无知"是刻意的、**高贵的无知**：

- **资产**：core 必须理解——因为是数字资产的物理生存（原图 / 缩略图 / hash）。
- **标签**：core 必须理解——因为是唯一通用的、无模式的关联机制。
- **其他一切**：core 不解析、不校验、不截断。原样存，原样读。

事实优于解释。`char:小薰` 是"指一个人"还是"指一个角色"——这是应用层的解释权，core 不管。

### 演进原则

任何字段调整都遵循：稳定字段硬编码进 dataclass schema，任意扩展字段一律走 metadata 字典透传。详见下文"已否决的设计"。

## 二、已否决的设计

历史决策记录。**当下设计的不变量与契约详见 `docs/spec/` 对应 spec**——这里只留被否决的方向，让未来 agent 知道哪些路走过不通。

- **`Asset` 持有 `captured_at`**：被否决。它记的是**扫描时刻**（与文件名时间戳逐秒相同，可从路径直接推出），不是业务语义，core 对它零需求。注意它与 `shot_date` 不是同一个量——`shot_date` 是**拍摄日期**（事件属性，Polaroid 层级），`captured_at` 是**扫描时刻**（文件属性），不要把两者混谈。
- **业务字段进 dataclass schema**（人名 / 事件名 / 评分等）：被否决。一律塞进 `metadata` 字典透传，core 不解析其内部结构。
- **core 引入数据库 / ORM / 复杂校验**：被否决。core 是单文件 YAML + 透传，保持极简。
- **为加速查询（`find_by_hash` / `find_by_path` / drop 的 `candidates`）建跨 yaml 的内存倒排索引、或为冷盘结果建缓存**：被否决。冷盘必须保持休眠（机械盘会因唤醒降低寿命 + 引入卡顿；NAS / 网络共享的网络握手延迟高且不可控），索引会让写失效状态机变复杂、把"内存副本 + 原子写"的一致性边界破坏掉。任何形式的"启动时扫描冷盘"或"监听冷盘变更"都是对架构的破坏。加速只能走"减少 explicit gesture 的次数"，例如 PUT 时前端已带 hash 后端就零冷盘读。
- **从文件名 / 内嵌时间戳 / 文件系统时间出发对扫描件内容做任何判断**：被否决。文件名（含时间戳）与 mtime 不携带内容语义——该文件名称可能为扫描仪自动生成/外部下载/拍摄等任意来源，翻面 / 重扫 / 补扫的时机无规律，文件之间的时间间隔/日期与其实质内容没有因果关系。**扫描仪一次只扫一面**：正反面在时间轴上相隔任意长——可能隔几天、可能补扫、可能跨批次，扫描时间序列不携带任何配对信息，**连弱信号 / 辅助证据都不构成**；任何"相邻扫描的一张大概率是另一面"的推理都是错的。内容判定、扫描件配对、拍摄日期推断等一律不得以文件名或mtime时间序列为依据。合法依据只有两个：批次分组 = **文件夹名称（因其来自人类手工分类）**；内容判定= **图像像素本身**。适用于一切现在与未来的导入 / 配对 / 分类工具。

### 已采纳但非平凡的架构保证

- **冷盘接触收束在 `polarscan/core/cold.py`**：作为架构层强制保证被采纳。任何代码要 `Image.open(cold_path)` / `Path(cold_path).read_*` / `open(cold_path, "rb")` 都必须经 cold.py 暴露的 `compute_hash` / `make_thumb_if_missing` / `open_full` / `read_full` 之一。`tests/test_no_direct_disk_io.py` 是 AST 守卫。详见 [cold-data-gateway spec](docs/spec/cold-data-gateway.md)。

## 三、不变量导航

不变量分布在 `docs/spec/` 下的独立 spec 中——**修改任何不变量前先读对应 spec + 同步更新涉及代码 + 测试**。新不变量必须先起 spec 再实现。

| spec | 主题 | STATUS |
|---|---|---|
| [architecture](docs/spec/architecture.md) | 顶层架构 + 数据分层 | IN PROGRESS |
| [cold-data-gateway](docs/spec/cold-data-gateway.md) | 冷盘接触网关 + 缩略图命名 + 冷热分层 | IMPLEMENTED |
| [asset-hash](docs/spec/asset-hash.md) | blake2b 128 hex 算法（前后端对齐） | IMPLEMENTED |
| [yaml-atomic-write](docs/spec/yaml-atomic-write.md) | yaml 原子写 + fsync + 容错 | PARTIAL |
| [api-facade](docs/spec/api-facade.md) | Polarscan 写入入口 + RLock | IMPLEMENTED |
| [library-root-semantics](docs/spec/library-root-semantics.md) | library_root 字段归属（应用层不直读） | IMPLEMENTED |
| [browse-grouping](docs/spec/browse-grouping.md) | 浏览页分组与组序（纯前端不变量） | IMPLEMENTED |
| [shot-date-semantics](docs/spec/shot-date-semantics.md) | 拍摄日期语义（候选日不自动填） | IMPLEMENTED |
| [ingest-scan](docs/spec/ingest-scan.md) | 存储区扫描 + 连连看批量入库 | IN PROGRESS |

完整 17 篇索引见 [docs/spec/README.md](docs/spec/README.md)。spec 系统的同步迭代规则与守卫见该 README。

## 不在本文件

| 你想知道 | 去哪里 |
|---|---|
| 项目是什么 / 怎么装 / 怎么跑 / API 表 / 标签前缀 | `README.md` |
| 哪些文件不进 git / 一次性脚本位置 | `.gitignore` |
| 行为真值（字段定义 / 路由逻辑） | `polarscan/core/` + `apps/` |
| 设计不变量 + 状态 | `docs/spec/` |
