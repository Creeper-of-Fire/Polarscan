"""/api/drop/identify 端点的隔离测试。

library_root 与 data_dir 都用临时目录；不依赖真实 F:盘。
"""
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
# ASGI helper: 支持 form 和 JSON body
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
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    form_body: dict[str, str] | None = None,
) -> _AsgiResponse:
    """直接调 ASGI 应用, 不依赖 TestClient。

    优先用 json_body; 没有则用 form_body.
    """
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        content_type = b"application/json"
    else:
        body = urlencode(form_body or {}).encode("utf-8")
        content_type = b"application/x-www-form-urlencoded"

    headers = [
        (b"host", b"testserver"),
        (b"content-type", content_type),
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

    start = next(m for m in messages if m["type"] == "http.response.start")
    content = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    response_headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in start["headers"]
    }
    return _AsgiResponse(start["status"], response_headers, content)


def _request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    form_body: dict[str, str] | None = None,
) -> _AsgiResponse:
    return asyncio.run(
        _request_asgi(method, path, json_body=json_body, form_body=form_body)
    )


# ============================================================
# 测试 fixtures
# ============================================================
class DropIdentifyTest(unittest.TestCase):
    """verify /api/drop/identify 在四种场景下的行为."""

    def setUp(self) -> None:
        # data_dir: 索引目录 (Polarscan 在此)
        self._tmp_data = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp_data.name)
        # library_root: 模拟 F:盘, 放 PNG
        self._tmp_lib = tempfile.TemporaryDirectory()
        self.library_root = Path(self._tmp_lib.name)

        # 在 library_root 下放三张 PNG, 内容不同 (颜色不同 → hash 不同)
        self.img_match = self.library_root / "img20260804_120000_match.png"
        self.img_other = self.library_root / "img20260804_130000_other.png"
        self.img_unrelated = self.library_root / "img20260805_unrelated.png"
        Image.new("RGB", (32, 24), color="red").save(self.img_match)
        Image.new("RGB", (32, 24), color="green").save(self.img_other)
        Image.new("RGB", (32, 24), color="blue").save(self.img_unrelated)
        # 记录每张图的真实 hash 和 stat
        self.hash_match = Asset.from_path(self.img_match).hash
        self.hash_other = Asset.from_path(self.img_other).hash
        assert self.hash_match and self.hash_other
        self.stat_match = self.img_match.stat()
        # 模拟浏览器端 lastModifiedMs → server 端 round(seconds) 的转换
        self.match_mtime_s = round(self.stat_match.st_mtime)

        # 替换 server 的 ps 实例 (e2e_test 同款做法)
        self.original_ps = server.ps
        server.ps = Polarscan(self.data_dir)
        # find_candidates_by_path 每次从 yaml 读 library_root——
        # 必须 save() 写 yaml 才能让 server 端调它时拿到正确值
        server.ps._data["library_root"] = str(self.library_root)
        server.ps.save()
        # 已索引 polaroid: p_match 用 img_match 的 hash + path
        server.ps.upsert_polaroid(
            Polaroid(
                id="p_match",
                assets=[
                    Asset(
                        role="front",
                        path=str(self.img_match),
                        hash=self.hash_match,
                    )
                ],
            )
        )
        server.ps.save()

    def tearDown(self) -> None:
        server.ps = self.original_ps
        self._tmp_data.cleanup()
        self._tmp_lib.cleanup()

    # ----------------- 必填字段校验 -----------------

    def test_missing_fields_400(self) -> None:
        """缺 name/size/lastModified_ms → 400."""
        r = _request("POST", "/api/drop/identify", json_body={"hash": "x"})
        self.assertEqual(r.status_code, 400)

    def test_invalid_json_400(self) -> None:
        """非法 JSON body → 400."""
        r = _request("POST", "/api/drop/identify", form_body={"not": "json"})
        # form_body 走到 form 路径, 端点尝试 json.loads(form 字符串) 会失败 → 400
        self.assertEqual(r.status_code, 400)

    # ----------------- by_hash -----------------

    def test_by_hash_hit(self) -> None:
        """客户端 hash 命中已索引 polaroid → by_hash 返回该 (pid, idx)."""
        r = _request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": "anything.png",
                "size": 1,
                "lastModified_ms": 0,
                "hash": self.hash_match,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["by_hash"], [{"pid": "p_match", "asset_idx": 0}])
        # 候选未提供正确的 triple, 所以 candidates 空
        self.assertEqual(body["candidates"], [])

    def test_by_hash_miss(self) -> None:
        """客户端 hash 不在索引 → by_hash 为空."""
        r = _request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": "x.png",
                "size": 1,
                "lastModified_ms": 0,
                "hash": "0" * 128,
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["by_hash"], [])

    def test_empty_hash_skips_lookup(self) -> None:
        """hash 为空字符串 → by_hash 空 (不抛错)."""
        r = _request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": "x.png",
                "size": 1,
                "lastModified_ms": 0,
                "hash": "",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["by_hash"], [])

    # ----------------- candidates -----------------

    def test_candidate_match_with_in_yaml_pid(self) -> None:
        """三元组命中 + 路径已在 yaml → candidate 含 in_yaml_pid."""
        r = _request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": self.img_match.name,
                "size": self.stat_match.st_size,
                "lastModified_ms": self.match_mtime_s * 1000,
                "hash": "",
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(body["candidates"][0]["path"], str(self.img_match))
        self.assertEqual(body["candidates"][0]["in_yaml_pid"], "p_match")

    def test_candidate_match_new_path(self) -> None:
        """三元组命中 + 路径不在 yaml → candidate.in_yaml_pid = None."""
        # 用一张未索引的图 (img_other)
        stat = self.img_other.stat()
        mtime_s = round(stat.st_mtime)
        r = _request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": self.img_other.name,
                "size": stat.st_size,
                "lastModified_ms": mtime_s * 1000,
                "hash": "",
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(body["candidates"][0]["in_yaml_pid"], None)

    def test_no_candidate_when_triple_mismatch(self) -> None:
        """三元组不对 → candidates 空."""
        r = _request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": "no_such_file.png",
                "size": 999,
                "lastModified_ms": 0,
                "hash": "",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["candidates"], [])

    def test_no_candidate_when_library_root_unset(self) -> None:
        """library_root 为 None → candidates 永远空."""
        # find_candidates_by_path 从 yaml 读——必须 save() 才能让它看到 None
        server.ps._data["library_root"] = None
        server.ps.save()
        r = _request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": self.img_match.name,
                "size": self.stat_match.st_size,
                "lastModified_ms": self.match_mtime_s * 1000,
                "hash": "",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["candidates"], [])

    # ----------------- 组合 -----------------

    def test_both_hash_and_candidate(self) -> None:
        """hash 命中 + 三元组命中 → 两者都返回."""
        r = _request(
            "POST",
            "/api/drop/identify",
            json_body={
                "name": self.img_match.name,
                "size": self.stat_match.st_size,
                "lastModified_ms": self.match_mtime_s * 1000,
                "hash": self.hash_match,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["by_hash"], [{"pid": "p_match", "asset_idx": 0}])
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(body["candidates"][0]["in_yaml_pid"], "p_match")


if __name__ == "__main__":
    unittest.main(verbosity=2)