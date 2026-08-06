# SPEC: api-facade（Polarscan 单例 + RLock + 唯一写入入口）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 类定义：`polarscan/api.py:Polarscan`
- 写入唯一入口：`polarscan/api.py:Polarscan.save`
- mutator：`upsert_polaroid` / `delete_polaroid` / `upsert_tag` / `set_tag_info` / `delete_tag`
- reader：`polaroids` / `polaroid` / `query_by_tag` / `query_by_prefix` / `tag_metadata` / `tag_info`
- 调用方：`apps/web/server.py`（所有 mutator 与 reader）

## 1. 背景

应用层（包括 server.py、未来的 CLI、其他 UI）必须通过 `Polarscan` 修改数据——**禁止直接 dump yaml**。`Polarscan` 是 in-memory 副本 + RLock 串行化的 facade。

## 2. 设计

### 单例 + in-memory 副本

```python
class Polarscan:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._data: dict[str, Any] = read_index(self.data_dir)  # 启动时一次
        self._lock = threading.RLock()
```

### RLock 串行化

- FastAPI sync 端点跑在线程池——`_data` 在迭代时必须不被并发修改
- 所有 mutator 与 reader 通过 `self._lock` 串行化
- 用 `threading.RLock` 允许方法间互相调用（`tag_info` 内部调 `tag_metadata`）不死锁
- 锁粒度是粗的——本应用写吞吐低，争用不是问题

### 写入流程

```
mutator → with self._lock: _data['polaroids'][i] = ... (内存)
save()  → with self._lock: write_index(self.data_dir, self._data) (原子写 yaml)
```

应用层只能通过 `save()` 写 yaml——这是 atomic write 的唯一入口。

## 3. 接口契约

### 读取

| 方法 | 行为 |
|---|---|
| `library_root` | 直接读 `_data["library_root"]`，无锁 |
| `polaroids()` | 列表（深拷贝 from dataclass） |
| `polaroid(pid)` | 单个或 None |
| `query_by_tag(tag)` | 精确 tag 包含 |
| `query_by_prefix(prefix)` | 前缀匹配 |
| `find_by_hash(h)` | 不缓存的 O(N) 扫 |
| `find_by_path(p)` | 不缓存的 O(N) 扫 |
| `tag_metadata(prefix)` | 标签池元数据 |
| `tag_info(prefix, key)` | 单个标签元数据 |
| `all_tags_with_prefix(prefix)` | 前缀下所有用过的 tag values |
| `all_tags_in_pool(prefix)` | 标签池列表 |
| `polaroids_with_tag(prefix, value)` | 用过此标签的 polaroid 列表 |
| `polaroid_index_of(pid)` | 索引查找 |
| `next_polaroid(pid)` / `prev_polaroid(pid)` / `next_untagged(pid)` | 导航 |
| `suggest_id(shot_date, tags)` | id 派生（不查重不写入） |
| `first_polaroid()` | 第一张 |

### 修改

| 方法 | 行为 |
|---|---|
| `reload()` | 重新读 yaml |
| `save()` | 写 yaml（atomic） |
| `upsert_polaroid(p)` | 内存 upsert |
| `delete_polaroid(pid)` | 内存删除 |
| `upsert_tag(prefix, key, meta)` | 标签池元数据 |
| `set_tag_info(prefix, key, info)` | 单个标签元数据（空 dict 时删除 key） |
| `set_tag_metadata(prefix, registry)` | 整桶替换 |
| `delete_tag(prefix, key)` | 标签池删除 |
| `thumb_path_for(polaroid, asset_idx)` | 浏览路径——thumb 命中零 IO；缺则 cold gate 单次冷盘读 |
| `append_files(pid, paths, roles)` | 追加资产（drop 增量） |

约束：
- 应用层禁止直接访问 `_data` 或 yaml 文件
- mutator 与 reader 同步通过 RLock
- `library_root` 直读字段是已知例外（半违规，见 [library-root-semantics](library-root-semantics.md)）

## 4. 验证

- `tests/test_polarscan_find.py`：find_by_hash / find_by_path / library_root 行为
- `tests/test_import_append_save.py`：append_files / upsert_polaroid + save 持久化
- `tests/test_id_gen.py`：suggest_id 派生
- `tests/smoke_test.py`：核心工作流（建/查/删）

## 5. 不变量

- `_data` 是 yaml 内容的 in-memory 副本——启动时一次读
- 所有 mutator 必须显式调 `save()` 才落盘（这是 Facade 的"明确写入"语义）
- `find_by_hash` / `find_by_path` 不缓存（见 commit 1 已否决的"为加速建索引"）

## 6. 演进约束

- 多库支持：每个 `data_dir` 一个 `Polarscan` 实例；RLock 隔离
- 锁粒度：当前粗锁够用；若未来高并发需拆细锁（按 polaroid id 或按 tags/polaroids 分桶）

## 7. 引用

- [yaml-atomic-write](yaml-atomic-write.md)：save 走 atomic write
- [cold-data-gateway](cold-data-gateway.md)：thumb_path_for 走 cold gate
- [library-root-semantics](library-root-semantics.md)：library_root 半违规