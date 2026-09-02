"""网页端路由的隔离端到端测试。

迁移到 Vue SPA + JSON API 后的测试模型：直接测后端 JSON API + form-encoded POST，
不再测旧 HTML 模板响应（templates/ 已删除）。

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

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


@dataclass
class AsgiResponse:
    """保存一次 ASGI 请求的响应结果。"""

    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.content)


async def request_asgi(
    method: str,
    path: str,
    data: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> AsgiResponse:
    """直接调用 ASGI 应用，避免依赖外部测试客户端。"""
    if data is not None and json_body is not None:
        raise ValueError("data and json_body are mutually exclusive")
    headers = [(b"host", b"testserver")]
    body = b""
    if data is not None:
        body = urlencode(data).encode("utf-8")
        headers.extend(
            [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"content-length", str(len(body)).encode("ascii")),
            ]
        )
    elif json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers.extend(
            [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ]
        )

    # 支持 query string: 调用方可传 "/thumb?path=...&hash=..."
    if "?" in path:
        path_only, query_string = path.split("?", 1)
        query_string_bytes = query_string.encode("utf-8")
    else:
        path_only = path
        query_string_bytes = b""

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path_only,
        "raw_path": path_only.encode("utf-8"),
        "query_string": query_string_bytes,
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "state": {},
        "extensions": {},
    }

    request_sent = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await server.app(scope, receive, send)

    start = next(message for message in messages if message["type"] == "http.response.start")
    content = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    response_headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start["headers"]
    }
    return AsgiResponse(start["status"], response_headers, content)


class WebEndToEndTest(unittest.TestCase):
    """使用临时索引和临时图片验证网页端 JSON API + form-encoded POST，不写入真实资料库。"""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._temp_dir.name)
        self.image_path = self.data_dir / "existing.png"
        Image.new("RGB", (40, 30), color="white").save(self.image_path)

        self.original_ps = server.ps
        server.ps = Polarscan(self.data_dir)
        server.ps.upsert_polaroid(
            Polaroid(
                id="existing_001",
                shot_date="2026-08-04",
                tags=["char:小薰"],
                notes="端到端测试基准记录",
                assets=[Asset.from_path(self.image_path, role="front")],
            )
        )
        server.ps.save()

    def tearDown(self) -> None:
        server.ps = self.original_ps
        self._temp_dir.cleanup()

    def request(
        self,
        method: str,
        path: str,
        data: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> AsgiResponse:
        return asyncio.run(request_asgi(method, path, data, json_body))

    def test_spa_catchall(self) -> None:
        """SPA 路由返回 index.html (无 Vite 时)；后端 JSON API 不受影响。"""
        response = self.request("GET", "/")
        self.assertEqual(response.status_code, 200)
        # dist 模式: 含 crossorigin + assets 引用; Vite 模式: 含 @vite/client
        # 两种都包含 "<div id=\"app\">"
        self.assertIn('<div id="app">', response.text)

    def test_api_polaroids_list(self) -> None:
        """GET /api/polaroids 返回 JSON summary 列表。"""
        response = self.request("GET", "/api/polaroids")
        self.assertEqual(response.status_code, 200)
        items = response.json()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "existing_001")
        self.assertEqual(items[0]["shot_date"], "2026-08-04")

    def test_api_polaroid_detail(self) -> None:
        """GET /api/polaroids/{pid} 返回 polaroid 详情。"""
        response = self.request("GET", "/api/polaroids/existing_001")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "existing_001")
        self.assertEqual(data["shot_date"], "2026-08-04")
        self.assertEqual(data["tags"], ["char:小薰"])
        self.assertEqual(data["notes"], "端到端测试基准记录")
        self.assertEqual(len(data["assets"]), 1)
        self.assertEqual(data["assets"][0]["role"], "front")

    def test_thumb_endpoint(self) -> None:
        """GET /thumb?path=&hash= 按 (path, hash) 生成缩略图。
        polaroid 索引不影响 thumb 可用性 — 走统一 by-path 入口。"""
        from urllib.parse import urlencode

        h = blake2b_hex(self.image_path)
        qs = urlencode({"path": str(self.image_path), "hash": h})
        response = self.request("GET", f"/thumb?{qs}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("image/"))

    def test_create_polaroid_via_put(self) -> None:
        """PUT /polaroid/{pid} 创建新 polaroid（C 路径）。
        返回 {ok, pid, asset_count, created=true}."""
        response = self.request(
            "PUT",
            "/polaroid/created_001",
            json_body={
                "id": "created_001",
                "shot_date": "2026-08-04",
                "tags": ["char:电电", "shot:pair"],
                "notes": "网页端创建",
                "assets": [
                    {
                        "role": "front",
                        "path": str(self.image_path),
                        "device": None,
                        "hash": blake2b_hex(self.image_path),
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["pid"], "created_001")
        self.assertEqual(body["asset_count"], 1)
        self.assertTrue(body["created"])
        # 验证 polaroid 真的被创建了
        server.ps.reload()
        p = server.ps.polaroid("created_001")
        self.assertIsNotNone(p)
        self.assertEqual(p.tags, ["char:电电", "shot:pair"])
        self.assertEqual(p.assets[0].role, "front")

    def test_update_polaroid_via_put(self) -> None:
        """PUT /polaroid/{pid} 替换现有 polaroid 状态（U 路径）。
        与 autosave 等价: 改 tags/shot_date/notes (assets 保持).
        created=false, 第二次同样 body PUT 仍幂等."""
        hash_now = blake2b_hex(self.image_path)
        body = {
            "id": "existing_001",
            "shot_date": "2026-08-05",
            "tags": ["char:小薰", "char:电电", "shot:solo"],
            "notes": "自动保存后的备注",
            "assets": [
                {
                    "role": "front",
                    "path": str(self.image_path),
                    "device": None,
                    "hash": hash_now,
                },
            ],
        }
        # 第一次: 更新
        r1 = self.request("PUT", "/polaroid/existing_001", json_body=body)
        self.assertEqual(r1.status_code, 200)
        self.assertFalse(r1.json()["created"])

        # 验证 polaroid 状态真的更新
        server.ps.reload()
        p = server.ps.polaroid("existing_001")
        self.assertEqual(p.shot_date, "2026-08-05")
        self.assertEqual(p.notes, "自动保存后的备注")
        self.assertEqual(p.tags, ["char:小薰", "char:电电", "shot:solo"])

        # 第二次: 幂等 - 同样的 body
        r2 = self.request("PUT", "/polaroid/existing_001", json_body=body)
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.json()["created"])

    def test_put_rejects_missing_hash(self) -> None:
        """asset 缺 hash → 400 (前端 dropzone invariant: 必须传 hash)."""
        response = self.request(
            "PUT",
            "/polaroid/no_hash_001",
            json_body={
                "id": "no_hash_001",
                "shot_date": None,
                "tags": [],
                "notes": "",
                "assets": [
                    {"role": "front", "path": str(self.image_path), "hash": ""},
                ],
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_put_rejects_empty_assets(self) -> None:
        """polaroid assets 空 → 400."""
        response = self.request(
            "PUT",
            "/polaroid/empty_001",
            json_body={
                "id": "empty_001",
                "shot_date": None,
                "tags": [],
                "notes": "",
                "assets": [],
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_put_rejects_id_mismatch(self) -> None:
        """url 上 pid 与 body.id 不一致 → 400."""
        response = self.request(
            "PUT",
            "/polaroid/url_pid",
            json_body={
                "id": "different_pid",
                "shot_date": None,
                "tags": [],
                "notes": "",
                "assets": [
                    {"role": "front", "path": str(self.image_path),
                     "hash": blake2b_hex(self.image_path)},
                ],
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_save_assets_via_put(self) -> None:
        """PUT 整体替换 polaroid, 改 asset role/device/metadata (同时验证整体替换语义)."""
        hash_now = blake2b_hex(self.image_path)
        response = self.request(
            "PUT",
            "/polaroid/existing_001",
            json_body={
                "id": "existing_001",
                "shot_date": "2026-08-04",  # 保持
                "tags": ["char:小薰"],  # 保持
                "notes": "端到端测试基准记录",  # 保持
                "assets": [
                    {
                        "role": "back",  # 改了
                        "path": str(self.image_path),
                        "device": "scanner_x",
                        "metadata": {"rating": 4},
                        "hash": hash_now,
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pid"], "existing_001")
        self.assertEqual(body["asset_count"], 1)

        server.ps.reload()
        p = server.ps.polaroid("existing_001")
        self.assertEqual(p.assets[0].role, "back")
        self.assertEqual(p.assets[0].device, "scanner_x")
        self.assertEqual(p.assets[0].metadata, {"rating": 4})

    def test_pool_edit(self) -> None:
        """POST /pool/{prefix}/{key}/edit 保存标签元数据 (含应援色字段)."""
        response = self.request(
            "POST",
            "/pool/char/北北鱼/edit",
            data={
                "canonical_name": "北北鱼Honomi",
                "aliases": "北北鱼, Honomi",
                "notes": "角色别名测试",
                "color_name": "粉色",
                "color_rgb": "#F9A7D6",
                "extra_json": "",
                "return_to": "/pool/char",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        server.ps.reload()
        info = server.ps.tag_info("char", "北北鱼")
        self.assertEqual(info["canonical_name"], "北北鱼Honomi")
        self.assertEqual(info["aliases"], ["北北鱼", "Honomi"])
        self.assertEqual(info["color_name"], "粉色")
        self.assertEqual(info["color_rgb"], "#F9A7D6")

        # 非法 RGB 被服务端丢弃 (清空), 不会爆掉
        response = self.request(
            "POST",
            "/pool/char/北北鱼/edit",
            data={
                "canonical_name": "北北鱼Honomi",
                "color_name": "",
                "color_rgb": "not-a-hex",
                "extra_json": "",
                "return_to": "/pool/char",
            },
        )
        self.assertEqual(response.status_code, 200)
        server.ps.reload()
        info = server.ps.tag_info("char", "北北鱼")
        self.assertEqual(info.get("color_rgb"), "")

    def test_delete_polaroid(self) -> None:
        """DELETE /polaroid/{pid} 删除 polaroid。"""
        response = self.request("DELETE", "/polaroid/existing_001")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertIsNone(server.ps.polaroid("existing_001"))

        # 后续 GET 返回 404
        response = self.request("GET", "/api/polaroids/existing_001")
        self.assertEqual(response.status_code, 404)

    def test_drop_identify(self) -> None:
        """POST /api/drop/identify 用 hash 反查 (无 library_root 时仅返回 by_hash)。"""
        response = self.request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": "x.png",
                "size": 1,
                "lastModified_ms": 1700000000000,
                "hash": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["by_hash"], [])
        # 没有 library_root, candidates 空
        self.assertIsInstance(body["candidates"], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)