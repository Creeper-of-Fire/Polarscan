# SPEC: yaml-atomic-write（_index.yaml 原子写 + fsync + 容错）

- **STATUS**: PARTIAL
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 写：`polarscan/core/storage.py:write_index`
- 读：`polarscan/core/storage.py:read_index`
- 调用方：`polarscan/api.py:Polarscan.save`（唯一入口）

## 1. 背景

`_index.yaml` 是项目唯一真相源。崩溃保护要求：写时不能产生半截文件；读时损坏不能导致进程启动失败。

## 2. 当前状态（PARTIAL）

### 已实施：atomic write

```python
# polarscan/core/storage.py:write_index
path = Path(library_root) / INDEX_FILENAME
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(".yaml.tmp")
with open(tmp, "w", encoding="utf-8") as f:
    yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False,
                   default_flow_style=False, width=4096)
tmp.replace(path)
```

- 先写 `.yaml.tmp` 再 `tmp.replace(path)`——`replace` 在 NTFS/ReFS 上原子
- `width=4096`：抑制 PyYAML 默认 80 字符硬换行（资产路径是长绝对路径）

### TODO（commit 2）：fsync + 容错

- `open(tmp, "w")` 未显式 `os.fsync(f.fileno())`——掉电时 yaml.tmp 可能半截
- `read_index` 对损坏 yaml 无 try/except——损坏时 `yaml.safe_load` 抛错而非回退默认
- **未实现备份机制**（`yaml.bak` / 多版本滚动）——见 README 讨论，本 spec 不展开

## 3. 目标（commit 2）

### fsync

```python
with open(tmp, "w", encoding="utf-8") as f:
    yaml.safe_dump(...)
    f.flush()
    os.fsync(f.fileno())  # 显式刷盘
tmp.replace(path)
```

### 容错（read_index）

```python
def read_index(library_root):
    path = Path(library_root) / INDEX_FILENAME
    if not path.exists():
        return _default_with_root(library_root)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return _normalize(data, library_root)
    except yaml.YAMLError:
        # 损坏 yaml 隔离: 重命名为 .yaml.broken-<unix-ts>
        broken = path.with_name(f"_index.yaml.broken-{int(time.time())}")
        path.rename(broken)
        return _default_with_root(library_root)
```

### 不引入备份

按用户拍板：备份机制暂时不实现——仅做 read 容错 + fsync。

## 4. 接口契约

- 唯一入口：`Polarscan.save()` 走 `write_index`——应用层禁止直写 yaml
- 读容错：损坏 yaml 必须**不抛错**（fail-soft）；损坏文件改名隔离以便事后分析
- `tmp.replace` 原子性：现代 NTFS/ReFS 上原子，但 OS 层面掉电仍可能 yaml.tmp 半截（fsync 后此风险消除）

## 5. 验证

- 已测试：`tests/test_import_append_save.py` / `tests/test_e2e_test.py` 验证 PUT/append 后的 yaml 持久化
- TODO（commit 2）：
  - 写入后立即 kill process → 重启仍能读到一致状态
  - 注入损坏 yaml → `read_index` 返回默认 + 损坏文件改名

## 6. 不变量

- `Polarscan.save()` 是 yaml 写入唯一入口
- `tmp.replace(path)` 原子性必须保持
- 损坏 yaml 不能导致进程启动失败（fail-soft）

## 7. 演进约束

- 备份机制（`.yaml.bak` / 多版本滚动）暂不实现；如未来需要，参考本 spec 的 fsync + 容错模式
- `width=4096` 是路径长度容限——若极端长路径出现需评估

## 8. 引用

- [api-facade](api-facade.md)：Polarscan.save 走本 spec
- [architecture § 3 数据分层](architecture.md)：yaml 是热层数据