"""import-from-files / append-files / save-assets 端点的隔离测试."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from PIL import Image

import apps.web.server as server
from polarscan.api import Polarscan
from polarscan.core import Asset, Polaroid


# ============================================================
# 复用 e2e_test 风格的 ASGI helper (支持 JSON body)
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

        self.original_ps = server.ps
        server.ps = Polarscan(self.data_dir)

    def tearDown(self) -> None:
        server.ps = self.original_ps
        self._tmp_data.cleanup()
        self._tmp_imgs.cleanup()


# ============================================================
# POST /api/polaroids/import-from-files
# ============================================================
class ImportFromFilesTest(ImportTestBase):
    """drop 创建 polaroid 的核心端点."""

    def test_creates_polaroid_with_multiple_assets(self) -> None:
        """多文件 → 多 assets + 缩略图生成 + yaml 写入."""
        r = _post("/api/polaroids/import-from-files", {
            "pid": "2026-08-04_test_aaaaaa",
            "path": [str(self.img_a), str(self.img_b)],
            "role": ["front", "back"],
            "date": "2026-08-04",
            "char": "test",
            "tags": ["event:demo"],
            "notes": "imported via drop",
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["pid"], "2026-08-04_test_aaaaaa")

        # 验证 yaml 写入
        server.ps.reload()
        p = server.ps.polaroid("2026-08-04_test_aaaaaa")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.shot_date, "2026-08-04")
        self.assertEqual(p.tags, ["event:demo"])
        self.assertEqual(p.notes, "imported via drop")
        self.assertEqual(len(p.assets), 2)
        self.assertEqual(p.assets[0].role, "front")
        self.assertEqual(p.assets[1].role, "back")
        # 每个 asset 都应有 hash 和 thumb
        for a in p.assets:
            self.assertIsNotNone(a.hash)
            self.assertTrue(
                a.thumb_path(server.ps.data_dir).exists()
            )

    def test_default_roles_when_omitted(self) -> None:
        """不传 role 时按 front/back/additional 默认."""
        r = _post("/api/polaroids/import-from-files", {
            "pid": "default_roles",
            "path": [str(self.img_a), str(self.img_b), str(self.img_c)],
            "date": None,
            "char": None,
            "tags": [],
            "notes": "",
        })
        self.assertEqual(r.status_code, 200)
        p = server.ps.polaroid("default_roles")
        assert p is not None
        self.assertEqual(
            [a.role for a in p.assets],
            ["front", "back", "additional"],
        )

    def test_pid_collision_409(self) -> None:
        """pid 已存在 → 409."""
        server.ps.upsert_polaroid(Polaroid(id="existing_id"))
        r = _post("/api/polaroids/import-from-files", {
            "pid": "existing_id",
            "path": [str(self.img_a)],
            "tags": [],
            "notes": "",
        })
        self.assertEqual(r.status_code, 409)

    def test_missing_path_400(self) -> None:
        """path 为空 → 400."""
        r = _post("/api/polaroids/import-from-files", {
            "pid": "no_paths",
            "path": [],
            "tags": [],
            "notes": "",
        })
        self.assertEqual(r.status_code, 400)

    def test_role_count_mismatch_400(self) -> None:
        """role 数量与 path 不一致 → 400."""
        r = _post("/api/polaroids/import-from-files", {
            "pid": "mismatch",
            "path": [str(self.img_a), str(self.img_b)],
            "role": ["front"],  # 只有 1 个 role, 但 2 个 path
            "tags": [],
            "notes": "",
        })
        self.assertEqual(r.status_code, 400)

    def test_missing_file_409(self) -> None:
        """路径不存在 → 409 (读取失败)."""
        r = _post("/api/polaroids/import-from-files", {
            "pid": "missing",
            "path": [str(self.img_dir / "no_such_file.png")],
            "tags": [],
            "notes": "",
        })
        self.assertEqual(r.status_code, 409)


# ============================================================
# POST /api/polaroids/{pid}/append-files
# ============================================================
class AppendFilesTest(ImportTestBase):
    def setUp(self) -> None:
        super().setUp()
        # 预先放一条 polaroid, 一个 front asset
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
# POST /bench/{pid}/save-assets
# ============================================================
class SaveAssetsTest(ImportTestBase):
    def setUp(self) -> None:
        super().setUp()
        # 已有 polaroid, 2 个 asset
        self.asset_a = Asset(role="front", path=str(self.img_a), captured_at="2026-08-04T10:00:00", hash="hash_a")
        self.asset_b = Asset(role="back", path=str(self.img_b), hash="hash_b")
        server.ps.upsert_polaroid(
            Polaroid(id="p1", assets=[self.asset_a, self.asset_b])
        )
        server.ps.save()

    def test_updates_role_and_metadata(self) -> None:
        """改 role / captured_at / device, 路径不变 → 成功."""
        r = _post("/bench/p1/save-assets", {
            "assets": [
                {"role": "front_v2", "path": str(self.img_a),
                 "captured_at": "2026-08-04T11:00:00", "device": "scanner_x"},
                {"role": "back_signature", "path": str(self.img_b),
                 "captured_at": None, "device": None},
            ],
        })
        self.assertEqual(r.status_code, 200)
        p = server.ps.polaroid("p1")
        assert p is not None
        self.assertEqual(p.assets[0].role, "front_v2")
        self.assertEqual(p.assets[0].captured_at, "2026-08-04T11:00:00")
        self.assertEqual(p.assets[0].device, "scanner_x")
        self.assertEqual(p.assets[1].role, "back_signature")
        # hash 保留
        self.assertEqual(p.assets[0].hash, "hash_a")
        self.assertEqual(p.assets[1].hash, "hash_b")

    def test_reorder_via_full_list(self) -> None:
        """通过传全列表重排顺序."""
        r = _post("/bench/p1/save-assets", {
            "assets": [
                {"role": "back", "path": str(self.img_b)},  # 原来 idx=1
                {"role": "front", "path": str(self.img_a)},  # 原来 idx=0
            ],
        })
        self.assertEqual(r.status_code, 200)
        p = server.ps.polaroid("p1")
        assert p is not None
        self.assertEqual(p.assets[0].path, str(self.img_b))
        self.assertEqual(p.assets[1].path, str(self.img_a))

    def test_rejects_new_path(self) -> None:
        """save-assets 不允许新 path → 400."""
        r = _post("/bench/p1/save-assets", {
            "assets": [
                {"role": "front", "path": str(self.img_a)},
                {"role": "back", "path": str(self.img_c)},  # c 不在当前 polaroid
            ],
        })
        self.assertEqual(r.status_code, 400)

    def test_rejects_empty(self) -> None:
        """空 assets 列表 → 400."""
        r = _post("/bench/p1/save-assets", {"assets": []})
        self.assertEqual(r.status_code, 400)

    def test_unknown_pid_404(self) -> None:
        r = _post("/bench/no_such/save-assets", {
            "assets": [{"role": "front", "path": str(self.img_a)}],
        })
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)