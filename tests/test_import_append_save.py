"""append-files / PUT /polaroid 端点的隔离测试.

PUT /polaroid/{pid} 为 C+U 合并的统一保存入口 (2026-08 重构):
  - 接受完整 polaroid JSON
  - assets[].hash 必须存在 (128 字符 blake2b), 由前端 dropzone 在浏览器算好后传
  - 幂等: 创建或整体替换
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from PIL import Image

import apps.web.server as server
from polarscan.api import Polarscan
from polarscan.core import Asset, Polaroid


def blake2b_hex(path: Path) -> str:
    """与前端 dropzone (JS blake2b, digest_size=64) 对齐的 128 hex 字符串."""
    h = hashlib.blake2b(digest_size=64)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
# ASGI helper: 支持 JSON body, 支持任意 method (POST/PUT)
# ============================================================
class _AsgiResponse:
    def __init__(self, status: int, headers: dict[str, str], content: bytes) -> None:
        self.status_code = status
        self.headers = headers
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.content)


async def _request_asgi(
    method: str, path: str, *, json_body: dict | None = None
) -> _AsgiResponse:
    body = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
    headers = [
        (b"host", b"testserver"),
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "state": {},
        "extensions": {},
    }
    sent = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await server.app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    content = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    response_headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in start["headers"]
    }
    return _AsgiResponse(start["status"], response_headers, content)


def _post(path: str, json_body: dict | None = None) -> _AsgiResponse:
    return asyncio.run(_request_asgi("POST", path, json_body=json_body))


def _put(path: str, json_body: dict | None = None) -> _AsgiResponse:
    return asyncio.run(_request_asgi("PUT", path, json_body=json_body))


# ============================================================
# 测试 fixtures
# ============================================================
class ImportTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_data = tempfile.TemporaryDirectory()
        self._tmp_imgs = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp_data.name)
        self.img_dir = Path(self._tmp_imgs.name)

        # 三张不同颜色 (hash 不同) 的 PNG
        self.img_a = self.img_dir / "a.png"
        self.img_b = self.img_dir / "b.png"
        self.img_c = self.img_dir / "c.png"
        Image.new("RGB", (32, 24), color="red").save(self.img_a)
        Image.new("RGB", (32, 24), color="green").save(self.img_b)
        Image.new("RGB", (32, 24), color="blue").save(self.img_c)

        # 真实 hash (前端 dropzone 算的就是这个)
        self.hash_a = blake2b_hex(self.img_a)
        self.hash_b = blake2b_hex(self.img_b)
        self.hash_c = blake2b_hex(self.img_c)

        self.original_ps = server.ps
        server.ps = Polarscan(self.data_dir)

    def tearDown(self) -> None:
        server.ps = self.original_ps
        self._tmp_data.cleanup()
        self._tmp_imgs.cleanup()


# ============================================================
# POST /api/polaroids/{pid}/append-files
# (与 PUT 解耦, 走 server 算 hash, 用于 dropzone 追加)
# ============================================================
class AppendFilesTest(ImportTestBase):
    def setUp(self) -> None:
        super().setUp()
        # 预先放一条 polaroid, 一个 front asset (hash 是简化的, append_files 用自己算的覆盖)
        self.existing_asset = Asset(role="front", path=str(self.img_a), hash="hash_a")
        server.ps.upsert_polaroid(
            Polaroid(id="p1", shot_date="2026-08-04", assets=[self.existing_asset])
        )
        server.ps.save()

    def test_appends_assets_with_default_roles(self) -> None:
        """默认 role: 已有 1 个 → 下一个 back; 已有 2 个 → 下一个 additional."""
        r = _post("/api/polaroids/p1/append-files", {
            "path": [str(self.img_b), str(self.img_c)],
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["pid"], "p1")
        self.assertEqual(body["asset_count"], 3)

        p = server.ps.polaroid("p1")
        assert p is not None
        self.assertEqual([a.role for a in p.assets], ["front", "back", "additional"])

    def test_explicit_roles(self) -> None:
        r = _post("/api/polaroids/p1/append-files", {
            "path": [str(self.img_b)],
            "role": ["back_signature"],
        })
        self.assertEqual(r.status_code, 200)
        p = server.ps.polaroid("p1")
        assert p is not None
        self.assertEqual(p.assets[1].role, "back_signature")

    def test_unknown_pid_404(self) -> None:
        r = _post("/api/polaroids/no_such/append-files", {
            "path": [str(self.img_b)],
        })
        self.assertEqual(r.status_code, 404)


# ============================================================
# PUT /polaroid/{pid}  (取代原 save-assets / autosave / /new)
# ============================================================
class PutPolaroidTest(ImportTestBase):
    def setUp(self) -> None:
        super().setUp()
        # 已有 polaroid, 2 个 asset
        self.asset_a = Asset(
            role="front",
            path=str(self.img_a),
            device="scanner_x",
            hash=self.hash_a,
        )
        self.asset_b = Asset(role="back", path=str(self.img_b), hash=self.hash_b)
        server.ps.upsert_polaroid(
            Polaroid(id="p1", shot_date="2026-08-04",
                     tags=["char:小薰"], notes="baseline",
                     assets=[self.asset_a, self.asset_b])
        )
        server.ps.save()

    def test_updates_role_and_metadata(self) -> None:
        """改 role / metadata / device, 路径不变 → 成功 (整体替换, fields 都来自 PUT body)."""
        r = _put("/polaroid/p1", {
            "id": "p1",
            "shot_date": "2026-08-04",  # 保持
            "tags": ["char:小薰"],      # 保持
            "notes": "baseline",         # 保持
            "assets": [
                {"role": "front_v2", "path": str(self.img_a),
                 "device": "scanner_x",
                 "metadata": {"rating": 5},
                 "hash": self.hash_a},
                {"role": "back_signature", "path": str(self.img_b),
                 "device": None, "metadata": {},
                 "hash": self.hash_b},
            ],
        })
        self.assertEqual(r.status_code, 200)
        p = server.ps.polaroid("p1")
        assert p is not None
        self.assertEqual(p.assets[0].role, "front_v2")
        self.assertEqual(p.assets[0].device, "scanner_x")
        self.assertEqual(p.assets[0].metadata, {"rating": 5})
        self.assertEqual(p.assets[1].role, "back_signature")
        self.assertEqual(p.assets[1].metadata, {})
        # hash 信任 PUT body 提供
        self.assertEqual(p.assets[0].hash, self.hash_a)
        self.assertEqual(p.assets[1].hash, self.hash_b)

    def test_reorder_via_full_list(self) -> None:
        """通过传全列表重排顺序."""
        r = _put("/polaroid/p1", {
            "id": "p1",
            "shot_date": "2026-08-04",
            "tags": ["char:小薰"],
            "notes": "baseline",
            "assets": [
                {"role": "back", "path": str(self.img_b), "hash": self.hash_b},  # 原来 idx=1
                {"role": "front", "path": str(self.img_a), "hash": self.hash_a},  # 原来 idx=0
            ],
        })
        self.assertEqual(r.status_code, 200)
        p = server.ps.polaroid("p1")
        assert p is not None
        self.assertEqual(p.assets[0].path, str(self.img_b))
        self.assertEqual(p.assets[1].path, str(self.img_a))

    def test_allows_new_path(self) -> None:
        """PUT 不限制 path 集合: 可以加新 path (与旧 save-assets 不同)."""
        r = _put("/polaroid/p1", {
            "id": "p1",
            "shot_date": "2026-08-04",
            "tags": ["char:小薰"],
            "notes": "baseline",
            "assets": [
                {"role": "front", "path": str(self.img_a), "hash": self.hash_a},
                {"role": "back", "path": str(self.img_b), "hash": self.hash_b},
                {"role": "additional", "path": str(self.img_c), "hash": self.hash_c},
            ],
        })
        self.assertEqual(r.status_code, 200)
        p = server.ps.polaroid("p1")
        assert p is not None
        self.assertEqual(len(p.assets), 3)
        self.assertEqual(p.assets[2].path, str(self.img_c))

    def test_removes_path_via_omit(self) -> None:
        """PUT 允许省略 (即删除) 已有 path."""
        r = _put("/polaroid/p1", {
            "id": "p1",
            "shot_date": "2026-08-04",
            "tags": ["char:小薰"],
            "notes": "baseline",
            "assets": [
                {"role": "front", "path": str(self.img_a), "hash": self.hash_a},
                # img_b 故意省略
            ],
        })
        self.assertEqual(r.status_code, 200)
        p = server.ps.polaroid("p1")
        assert p is not None
        self.assertEqual(len(p.assets), 1)

    def test_rejects_empty_assets(self) -> None:
        """空 assets 列表 → 400."""
        r = _put("/polaroid/p1", {
            "id": "p1",
            "shot_date": "2026-08-04",
            "tags": ["char:小薰"],
            "notes": "baseline",
            "assets": [],
        })
        self.assertEqual(r.status_code, 400)

    def test_rejects_missing_hash(self) -> None:
        """asset 缺 hash → 400 (前端 dropzone invariant: 必须传 hash)."""
        r = _put("/polaroid/p1", {
            "id": "p1",
            "shot_date": "2026-08-04",
            "tags": ["char:小薰"],
            "notes": "baseline",
            "assets": [
                {"role": "front", "path": str(self.img_a), "hash": ""},
            ],
        })
        self.assertEqual(r.status_code, 400)

    def test_idempotent_same_body_twice(self) -> None:
        """PUT 同一 body 两次: 第二次 created=False, 状态不变."""
        body = {
            "id": "p1",
            "shot_date": "2026-08-04",
            "tags": ["char:小薰"],
            "notes": "baseline",
            "assets": [
                {"role": "front", "path": str(self.img_a), "hash": self.hash_a},
                {"role": "back", "path": str(self.img_b), "hash": self.hash_b},
            ],
        }
        r1 = _put("/polaroid/p1", body)
        r2 = _put("/polaroid/p1", body)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r1.json()["created"])
        self.assertFalse(r2.json()["created"])

    def test_creates_new_polaroid(self) -> None:
        """PUT 一个之前不存在的 pid → 创建 (created=true)."""
        body = {
            "id": "p_new",
            "shot_date": "2026-08-06",
            "tags": ["char:小薰"],
            "notes": "新拍立得",
            "assets": [
                {"role": "front", "path": str(self.img_a), "hash": self.hash_a},
            ],
        }
        r = _put("/polaroid/p_new", body)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["created"])
        server.ps.reload()
        p = server.ps.polaroid("p_new")
        assert p is not None
        self.assertEqual(p.tags, ["char:小薰"])

    def test_id_mismatch_rejected(self) -> None:
        """url 上 pid 与 body.id 不一致 → 400."""
        r = _put("/polaroid/url_pid", {
            "id": "different_pid",
            "shot_date": None,
            "tags": [],
            "notes": "",
            "assets": [
                {"role": "front", "path": str(self.img_a), "hash": self.hash_a},
            ],
        })
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)