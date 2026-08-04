"""网页端路由的隔离端到端测试。

迁移到 Vue SPA + JSON API 后的测试模型：直接测后端 JSON API + form-encoded POST，
不再测旧 HTML 模板响应（templates/ 已删除）。
"""
from __future__ import annotations

import asyncio
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
                tags=["char:strawberry"],
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
        self.assertEqual(data["tags"], ["char:strawberry"])
        self.assertEqual(data["notes"], "端到端测试基准记录")
        self.assertEqual(len(data["assets"]), 1)
        self.assertEqual(data["assets"][0]["role"], "front")

    def test_thumb_endpoint(self) -> None:
        """GET /thumb/{pid} 返回图片字节。"""
        response = self.request("GET", "/thumb/existing_001")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("image/"))

    def test_create_polaroid_via_post(self) -> None:
        """POST /new (form-encoded) 创建 polaroid，返回 JSON {ok, pid}。"""
        response = self.request(
            "POST",
            "/new",
            data={
                "pid": "created_001",
                "asset_paths": str(self.image_path),
                "tags": "char:hime, shot:pair",
                "shot_date": "2026-08-04",
                "notes": "网页端创建",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["pid"], "created_001")
        # 验证 polaroid 真的被创建了
        self.assertIsNotNone(server.ps.polaroid("created_001"))

    def test_autosave(self) -> None:
        """POST /bench/{pid}/autosave 增量保存 tags / shot_date / notes。"""
        response = self.request(
            "POST",
            "/bench/existing_001/autosave",
            data={
                "tags": "char:strawberry, char:hime, shot:solo",
                "shot_date": "2026-08-05",
                "notes": "自动保存后的备注",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["tags"], ["char:strawberry", "char:hime", "shot:solo"])
        self.assertEqual(body["shot_date"], "2026-08-05")

        # 验证 polaroid 状态真的更新
        server.ps.reload()
        p = server.ps.polaroid("existing_001")
        self.assertEqual(p.shot_date, "2026-08-05")
        self.assertEqual(p.notes, "自动保存后的备注")
        self.assertIn("char:hime", p.tags)

    def test_pool_edit(self) -> None:
        """POST /pool/{prefix}/{key}/edit 保存标签元数据。"""
        response = self.request(
            "POST",
            "/pool/char/hime/edit",
            data={
                "canonical_name": "姬",
                "aliases": "hime, 小姬",
                "notes": "角色别名测试",
                "extra_json": "",
                "return_to": "/pool/char",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        server.ps.reload()
        info = server.ps.tag_info("char", "hime")
        self.assertEqual(info["canonical_name"], "姬")
        self.assertEqual(info["aliases"], ["hime", "小姬"])

    def test_delete_polaroid(self) -> None:
        """POST /bench/{pid}/delete 删除 polaroid。"""
        response = self.request("POST", "/bench/existing_001/delete")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertIsNone(server.ps.polaroid("existing_001"))

        # 后续 GET 返回 404
        response = self.request("GET", "/api/polaroids/existing_001")
        self.assertEqual(response.status_code, 404)

    def test_save_assets_json(self) -> None:
        """POST /bench/{pid}/save-assets (JSON) 原子替换 assets。"""
        response = self.request(
            "POST",
            "/bench/existing_001/save-assets",
            json_body={
                "assets": [
                    {"role": "back", "path": str(self.image_path), "captured_at": None, "device": None},
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