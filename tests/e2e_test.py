"""网页端路由的隔离端到端测试。"""
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
) -> AsgiResponse:
    """直接调用 ASGI 应用，避免依赖外部测试客户端。"""
    body = urlencode(data or {}).encode("utf-8")
    headers = [(b"host", b"testserver")]
    if data is not None:
        headers.extend(
            [
                (b"content-type", b"application/x-www-form-urlencoded"),
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
    """使用临时索引和临时图片验证网页端，不写入真实资料库。"""

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
    ) -> AsgiResponse:
        return asyncio.run(request_asgi(method, path, data))

    def test_web_workflow(self) -> None:
        """验证浏览、新建、自动保存、标签池编辑、缩略图与删除。"""
        response = self.request("GET", "/")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/bench/existing_001")

        response = self.request("GET", "/bench/existing_001")
        self.assertEqual(response.status_code, 200)
        self.assertIn("端到端测试基准记录", response.text)

        response = self.request("GET", "/thumb/existing_001")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("image/"))

        response = self.request(
            "POST",
            "/new",
            {
                "pid": "created_001",
                "asset_path": str(self.image_path),
                "tags": "char:hime, shot:pair",
                "shot_date": "2026-08-04",
                "notes": "网页端创建",
            },
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/bench/created_001")

        response = self.request(
            "POST",
            "/bench/created_001/autosave",
            {
                "tags": "char:hime, shot:solo",
                "shot_date": "2026-08-05",
                "notes": "自动保存后的备注",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        response = self.request(
            "POST",
            "/pool/char/hime/edit",
            {
                "canonical_name": "姬",
                "aliases": "hime, 小姬",
                "notes": "角色别名测试",
                "extra_json": "",
                "return_to": "/bench/created_001",
            },
        )
        self.assertEqual(response.status_code, 303)
        server.ps.reload()
        self.assertEqual(server.ps.tag_info("char", "hime")["canonical_name"], "姬")

        response = self.request("POST", "/bench/created_001/delete", {})
        self.assertEqual(response.status_code, 303)
        self.assertIsNone(server.ps.polaroid("created_001"))

        response = self.request("GET", "/bench/created_001")
        self.assertEqual(response.status_code, 404)
        self.assertIn("未找到拍立得", response.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
