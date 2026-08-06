"""Polarscan web server: FastAPI + Vue SPA.

启动：
    python -m apps.web.server
浏览器打开 http://127.0.0.1:8765

开发模式（前端热更新）：
    终端 A: pnpm dev          # 启动 Vite (5173)
    终端 B: python -m apps.web.server  # 自动检测到 Vite 后代理 SPA 请求到 Vite

也可用 pnpm dev 同时跑（concurrently），但 Vite dev 端口是 5173 而本服务是 8765，
本服务会自动检测 5173 是否可用，可用就代理过去，否则用 frontend/dist 静态产物。
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from polarscan.api import Polarscan
from polarscan.core.find_candidates import find_candidates_by_path
from polarscan.core.library_resolver import Triple


logger = logging.getLogger("polarscan.web")


# ============================================================
# 配置：data_dir 存放索引与缩略图
# ============================================================
DATA_DIR = Path(__file__).resolve().parent.parent.parent
WEB_DIR = Path(__file__).parent
SPA_DIR = WEB_DIR.parent.parent / "frontend" / "dist"
VITE_DEV_URL = "http://127.0.0.1:5173"


# ============================================================
# 启动时探测 Vite dev server 是否可用
# ============================================================
def _detect_vite() -> bool:
    """启动时探测 Vite dev server (127.0.0.1:5173) 是否可用。

    如果可用，FastAPI 会把所有 SPA 请求代理到 Vite（HMR 生效）；
    否则用 frontend/dist 静态产物。
    """
    try:
        r = httpx.get(VITE_DEV_URL, timeout=1.0)
        if r.status_code == 200:
            logger.info(f"Vite dev detected at {VITE_DEV_URL}; SPA will be proxied there")
            return True
    except (httpx.HTTPError, OSError):
        pass
    logger.info(f"Vite dev not detected; SPA will be served from {SPA_DIR}")
    return False


VITE_AVAILABLE = _detect_vite()


# ============================================================
# 单例 + 静态资源
# ============================================================
ps = Polarscan(DATA_DIR)
app = FastAPI(title="Polarscan")
if SPA_DIR.exists() and not VITE_AVAILABLE:
    # Vite dev 模式下不挂载 dist/assets，避免冲突；dev 时由 catch-all 代理
    app.mount("/assets", StaticFiles(directory=str(SPA_DIR / "assets")), name="spa-assets")


def reload_ps() -> None:
    ps.reload()


def _polaroid_summary(p) -> dict:
    """list / 池浏览用的轻量 summary.

    含 cover_asset = assets[0] (或 None) - 给 ListView 的卡片显示缩略图用,
    后端拼 URL 模板是组件的事, 这里只给业务对象 (id + cover_asset.hash).
    tags 字段供 ListView 客户端 chip 过滤 (AND) 使用 — 列表场景本就需要 tags,
    补这一个字段不破坏现有 summary 的轻量性.
    """
    cover = p.assets[0] if p.assets else None
    return {
        "id": p.id,
        "shot_date": p.shot_date,
        "tags": list(p.tags),
        "cover_asset": asdict(cover) if cover is not None else None,
    }


def _polaroid_to_dict(p) -> dict:
    return asdict(p)


def _pool_items(prefix: str) -> list[dict]:
    items = ps.all_tags_in_pool(prefix)
    enriched = []
    for k, meta in items.items():
        count = len(ps.polaroids_with_tag(prefix, k))
        enriched.append({"key": k, "meta": meta, "count": count})
    enriched.sort(key=lambda x: (-x["count"], x["key"]))
    return enriched


# ============================================================
# JSON API（Vue SPA 使用）
# ============================================================
@app.get("/api/polaroids")
def api_polaroids(tag: Optional[str] = None):
    """全部 polaroid summary，或按 tag 过滤。

    tag 形如 'char:my_push' 或 'shot:pair'。无冒号视为完整 tag 查询。
    """
    if tag:
        return [_polaroid_summary(p) for p in ps.query_by_tag(tag)]
    return [_polaroid_summary(p) for p in ps.polaroids()]


@app.get("/api/polaroids/{pid}")
def api_polaroid(pid: str):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, f"未找到拍立得：{pid}")
    return _polaroid_to_dict(p)


@app.get("/api/polaroids/{pid}/goto/{direction}")
def api_goto(pid: str, direction: str):
    """返回跳转目标 id，不直接重定向（前端用 Vue Router push）。"""
    if direction == "prev":
        target = ps.prev_polaroid(pid)
    elif direction == "next":
        target = ps.next_polaroid(pid)
    elif direction == "untagged":
        target = ps.next_untagged(pid)
    else:
        raise HTTPException(400, "导航方向必须是 prev、next 或 untagged")
    return {"target": target.id if target else None}


@app.get("/api/all-tags")
def api_all_tags(prefix: Optional[str] = None):
    """返回已用 tag values。prefix 指定时返回单前缀列表，否则按前缀分组。"""
    if prefix:
        return ps.all_tags_with_prefix(prefix)
    return {
        "char": ps.all_tags_with_prefix("char"),
        "event": ps.all_tags_with_prefix("event"),
        "theme": ps.all_tags_with_prefix("theme"),
        "collection": ps.all_tags_with_prefix("collection"),
        "composite": ps.all_tags_with_prefix("composite"),
        "moment": ps.all_tags_with_prefix("moment"),
        "shot": ps.all_tags_with_prefix("shot"),
        "sig": ps.all_tags_with_prefix("sig"),
    }


@app.get("/api/pool/{prefix}")
def api_pool_index(prefix: str):
    return _pool_items(prefix)


@app.get("/api/pool/{prefix}/{key}")
def api_pool_get(prefix: str, key: str):
    info = ps.tag_info(prefix, key)
    used_by = ps.polaroids_with_tag(prefix, key)
    return {
        "prefix": prefix,
        "key": key,
        "info": info,
        "used_by": [_polaroid_summary(p) for p in used_by],
    }


@app.get("/api/suggest-id")
def api_suggest_id(shot_date: Optional[str] = None, primary_char: Optional[str] = None):
    primary_tags = [f"char:{primary_char}"] if primary_char else []
    return {"pid": ps.suggest_id(shot_date, primary_tags)}


# ============================================================
# POST 端点：form-encoded 接收（前端 FormData），返回 JSON
# ============================================================
# ============================================================
# 写 Polaroid 状态: 单一 PUT (C+U 合并)
#
# 设计原则 (2026-08 重构):
# - 单一 PUT endpoint 取代原本的 POST /new, POST /bench/{pid}/autosave,
#   POST /bench/{pid}/save-assets. C 和 U 在此合并.
# - 幂等: PUT 同一 polaroid 状态两次 → 同一最终状态.
# - assets[].hash 由前端提供且必须存在 (128 字符, blake2b); 后端信任, 不读 F: 盘.
#   前端 dropzone 在浏览器侧用 blake2b 算 hash, 同时该 hash 又是 ?v= cache-bust 的依据.
# ============================================================
@app.put("/polaroid/{pid}")
async def api_save_polaroid(pid: str, request: Request):
    """幂等创建或替换 polaroid.

    Body: 完整 polaroid JSON ({id, shot_date, tags, notes, assets[]}).
    Assets 每项含 role/path/device/metadata/hash; hash 必须 128 字符.

    pid 不存在 → 创建; pid 存在 → 整体替换 (assets 也整体替换, 允许任意路径集合).
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "请求体必须是合法 JSON")

    if not isinstance(body, dict):
        raise HTTPException(400, "请求体必须是 polaroid 对象")

    from polarscan.core.index import Polaroid
    try:
        polaroid = Polaroid.from_dict(body)
    except Exception as e:
        raise HTTPException(400, f"polaroid 字段格式错: {e}")

    if polaroid.id != pid:
        raise HTTPException(400, f"url 上 pid ({pid}) 与 body.id ({polaroid.id}) 不一致")

    if not polaroid.assets:
        raise HTTPException(400, "polaroid 必须至少有一个 asset")

    for idx, asset in enumerate(polaroid.assets):
        if not asset.hash or len(asset.hash) != 128:
            raise HTTPException(
                400,
                f"assets[{idx}].hash 必须存在且为 128 字符 (前端 dropzone 算好后传)",
            )

    is_new = ps.polaroid(pid) is None
    ps.upsert_polaroid(polaroid)
    ps.save()
    return {
        "ok": True,
        "pid": polaroid.id,
        "asset_count": len(polaroid.assets),
        "created": is_new,
    }


@app.delete("/polaroid/{pid}")
def api_delete_polaroid(pid: str):
    if not ps.delete_polaroid(pid):
        raise HTTPException(404, "未找到拍立得")
    ps.save()
    return {"ok": True}


@app.post("/pool/{prefix}/{key}/edit")
async def pool_edit_save(
    prefix: str,
    key: str,
    canonical_name: str = Form(""),
    aliases: str = Form(""),
    notes: str = Form(""),
    extra_json: str = Form(""),
):
    info = dict(ps.tag_info(prefix, key))
    info["canonical_name"] = canonical_name.strip()
    info["aliases"] = [a.strip() for a in aliases.split(",") if a.strip()]
    info["notes"] = notes.strip()
    if extra_json.strip():
        try:
            extras = json.loads(extra_json)
            if isinstance(extras, dict):
                info.update(extras)
        except json.JSONDecodeError:
            pass
    ps.set_tag_info(prefix, key, info)
    ps.save()
    return {"ok": True}


@app.post("/pool/{prefix}/{key}/delete")
async def pool_delete(prefix: str, key: str):
    ps.delete_tag(prefix, key)
    ps.save()
    return {"ok": True}


@app.post("/reload")
def reload_endpoint():
    reload_ps()
    return {"ok": True}


# ============================================================
# 图片 / 缩略图 — 统一 by-path 入口 (不依赖 polaroid 索引)
#
# 设计动机 (2026-08 重构):
# - 旧 contract (/thumb/{pid}/{idx}, /img/{pid}/{idx}) 要求服务端先按 pid 找到 polaroid,
#   再按 idx 找 asset. 这导致 NewView 拖入后 polaroid 未索引时无法预览.
# - 新 contract 接收 (path, hash): path 直接定位 F: 盘文件, hash 派生 thumb 文件名.
#   polaroid 是否索引与 thumb 可用性解耦 — 拖入即可预览, 无需"先创建再预览"分支.
# - PUT 仍无副作用: 服务端只在 GET 时按需生成 thumb (单次 F: 盘 IO).
# ============================================================
from polarscan.core.asset_thumb import (
    SHORT_HASH_LEN,
)
from polarscan.core.cold import (
    make_thumb_if_missing,
    open_full as cold_open_full,
)



@app.get("/thumb")
def thumb_by_path(path: str, hash: str):
    """统一缩略图入口: by (path, hash). 不依赖 polaroid 索引.

    - 缩略图路径由 `polarscan.core.index.thumb_path_for` 派生——单源真值,
      与 `Asset.thumb_path` 共用, 不在此硬编码命名公式.
    - thumb 已存在 → 直接返回 (零 IO).
    - thumb 不存在 + 源文件存在 → 经 cold gate 单次冷盘读生成 (之后缓存命中).
    - thumb 不存在 + 源文件不存在 → 404.

    冷盘接触全部经 `cold.make_thumb_if_missing`——本路由内不允许 `Image.open(path)`.
    """
    if not hash or len(hash) < SHORT_HASH_LEN:
        raise HTTPException(400, f"hash 必须至少 {SHORT_HASH_LEN} 字符")
    tp = make_thumb_if_missing(DATA_DIR, path, hash)
    if tp is None or not tp.exists():
        # cold gate 在 hash 缺失/太短 或 src 缺失时返回 None
        raise HTTPException(404, f"无法生成缩略图: path={path}")
    return FileResponse(tp)


@app.get("/img")
def img_by_path(path: str):
    """统一原图入口: by path. 仅 lightbox 点击时调用.

    冷盘接触经 `cold.open_full`（流式句柄，扫描大图 + NAS 友好）——本路由内
    不允许 `Path(src).read_bytes()` 或 `open(src, 'rb')` 等裸 IO.
    """
    src = Path(path)
    if not src.exists():
        raise HTTPException(404, f"源文件不存在: {path}")
    return StreamingResponse(cold_open_full(src), media_type="image/png")


# ============================================================
# drop 工作流
# ============================================================
@app.post("/api/drop/identify")
async def api_drop_identify(request: Request):
    """drop 工作流的 identify 端点（零 F:盘读 IO）。"""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "请求体必须是合法 JSON")

    name = body.get("name")
    size = body.get("size")
    last_modified_ms = body.get("lastModified_ms")
    h = body.get("hash") or ""
    if not isinstance(last_modified_ms, (int, float)):
        raise HTTPException(400, "缺少 lastModified_ms（数字）")

    by_hash: list[dict] = []
    for hit_pid, idx in ps.find_by_hash(h):
        by_hash.append({"pid": hit_pid, "asset_idx": idx})

    candidates: list[dict] = []
    qt = Triple(
        name=name,
        size=int(size),
        mtime=round(last_modified_ms / 1000.0),
    )
    # find_candidates_by_path 从 ps.data 提取 library_root——应用层不直接接触 schema 字段
    # library_root 缺失时返回空结果集（不抛错）—— drop 工作流优雅降级
    result = find_candidates_by_path(ps.data, [qt])
    for cand in result.get(qt, []):
        path_str = str(cand.path)
        in_yaml_hits = ps.find_by_path(path_str)
        in_yaml_pid = in_yaml_hits[0][0] if in_yaml_hits else None
        candidates.append({
            "path": path_str,
            "in_yaml_pid": in_yaml_pid,
            # 完整命中位置列表 (pid + asset_idx) - 用于前端 force-add dialog
            # in_yaml_pid 保留为兼容字段 (例如老版测试 / 第三方脚本)
            "in_yaml_hits": [
                {"pid": hit_pid, "asset_idx": hit_idx}
                for hit_pid, hit_idx in in_yaml_hits
            ],
        })

    return {"by_hash": by_hash, "candidates": candidates}


@app.post("/api/polaroids/{pid}/append-files")
async def api_append_files(pid: str, request: Request):
    """把 F:盘路径集合追加到现有 polaroid。"""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "请求体必须是合法 JSON")

    paths = body.get("path") or []
    roles = body.get("role")

    if not isinstance(paths, list) or not paths:
        raise HTTPException(400, "缺少 path（非空列表）")
    if roles is not None and not isinstance(roles, list):
        raise HTTPException(400, "role 必须是列表或 null")

    try:
        polaroid = ps.append_files(pid, paths=paths, roles=roles)
    except ValueError as e:
        msg = str(e)
        if "未找到" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)
    except OSError as e:
        raise HTTPException(409, f"读取文件失败: {e}")

    return {"pid": polaroid.id, "asset_count": len(polaroid.assets)}


# ============================================================
# Vue SPA catch-all: dev 模式代理到 Vite，否则用 dist 静态文件
# ============================================================
async def _proxy_to_vite(request: Request) -> Response:
    """把 SPA 请求代理到 Vite dev server (127.0.0.1:5173)。

    Vite 自带 HMR 需要 streaming 响应（EventStream），所以用 stream + StreamingResponse。
    """
    url = f"{VITE_DEV_URL}{request.url.path}"
    if request.url.query:
        url += "?" + str(request.url.query)

    # 透传 request headers (排除 hop-by-hop)
    skip_fwd = {"host", "connection", "content-length", "transfer-encoding"}
    fwd_headers = {k: v for k, v in request.headers.items() if k.lower() not in skip_fwd}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=2.0)) as client:
        try:
            vite_req = client.build_request("GET", url, headers=fwd_headers)
            vite_resp = await client.send(vite_req, stream=True)
        except (httpx.HTTPError, OSError) as e:
            logger.warning(f"Vite proxy failed: {e}")
            return JSONResponse({"error": f"Vite dev unavailable: {e}"}, status_code=502)

        # 透传 response headers (排除 hop-by-hop 和 content-length，由 Starlette 算)
        skip_resp = {"content-length", "transfer-encoding", "connection"}
        out_headers = {k: v for k, v in vite_resp.headers.items() if k.lower() not in skip_resp}

        return StreamingResponse(
            vite_resp.aiter_raw(),
            status_code=vite_resp.status_code,
            headers=out_headers,
        )


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_catch_all(full_path: str, request: Request):
    """Vue Router SPA 接管。

    开发模式 (Vite 在跑): 代理到 Vite，热更新生效
    生产模式 (dist 已构建): 用 frontend/dist 静态文件
    """
    if VITE_AVAILABLE:
        return await _proxy_to_vite(request)

    if full_path:
        candidate = SPA_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
    index_html = SPA_DIR / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return JSONResponse(
        {
            "error": "SPA 未构建。请先运行 `pnpm build`（生产模式）或 `pnpm dev`（开发模式，端口 5173）。"
        },
        status_code=503,
    )


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")