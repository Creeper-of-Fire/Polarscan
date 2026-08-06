# SPEC: library-root-semantics（library_root 字段归属）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 字段定义：`polarscan/core/storage.py:_default`（yaml 顶层字段）
- 字段 bootstrap：`_bootstrap.py`（一次性脚本，不入 git）
- 应用层入口：`polarscan/core/find_candidates.py:find_candidates_by_path`（封装 library_root 访问）
- 数据视图：`polarscan/api.py:Polarscan.data`（应用层只读视图）
- 路径反查实现：`polarscan/core/library_resolver.py:identify_candidates`
- 调用方：`apps/web/server.py`（`api_drop_identify` 调 `find_candidates_by_path(ps.data, [qt])`）

## 1. 背景

`library_root` 是 yaml 顶层字段，标识"实物根"（F 盘 / NAS）位置。它服务于 drop 工作流的路径反查——`identify_candidates` 需要遍历整个 library_root。

## 2. 当前状态

- 字段由 `_bootstrap.py` 一次性脚本写入 yaml（不在仓库内）
- 默认值：`storage.py:_default` 让 `library_root` 等于 `data_dir` 自身（bootstrap 前 fallback）
- 运行时读取：**应用层不直接读 `library_root` 字段**——通过 `core.find_candidates_by_path(ps.data, queries)` 让 core 内部提取

## 3. 设计

### 字段归属

- `library_root` 是 yaml 顶层字段——bootstrap 脚本写入一次
- 运行时由 core 实物层封装；应用层不得直读 schema 字段

### 接口契约

```python
# polarscan/core/find_candidates.py
def find_candidates_by_path(
    data: Mapping[str, Any],    # Polarscan.data 视图（只读 dict 浅拷贝）
    queries: Iterable[Triple],
) -> dict[Triple, list[Candidate]]:
    """从 data 提取 library_root，调 identify_candidates。
    library_root 缺失时返回空结果集——drop 工作流优雅降级。
    """
```

应用层调用：
```python
# apps/web/server.py
from polarscan.core.find_candidates import find_candidates_by_path
from polarscan.core.library_resolver import Triple

result = find_candidates_by_path(ps.data, [qt])
```

应用层**不**直接接触 `library_root`——所有访问通过 `Polarscan.data` 视图 + core 函数。

## 4. 验证

- `tests/test_drop_identify.py`：drop identify 行为
- `tests/test_library_resolver.py`：`identify_candidates` 隔离测试
- `tests/test_polarscan_find.py`：原本测试 `Polarscan.library_root` property 的 `LibraryRootTest` 已删除
- `tests/test_spec_consistency.py`：spec-code 链接自动校验

## 5. 不变量

- `library_root` 是 yaml 顶层字段——bootstrap 脚本写入一次
- 运行时由 core 实物层封装；应用层不得直读 schema 字段
- 多个 data_dir 共享同一 `library_root` 是允许的（未来的多库支持）

## 6. 演进约束

- 应用层若需访问 library_root 字段，必须通过 core 函数；禁止直接 `ps._data["library_root"]` 之类
- `Polarscan.data` 是浅拷贝——应用层不能修改返回值影响 Polarscan 内存状态

## 7. 引用

- [cold-data-gateway](cold-data-gateway.md)：冷盘接触唯一面
- [drop-identify](drop-identify.md)：drop 工作流（`find_candidates_by_path` 的当前 caller）
- [api-facade](api-facade.md)：Polarscan.data 视图