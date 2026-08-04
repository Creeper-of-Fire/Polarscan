"""本地网页应用：工作台界面与标签池增删改查。

启动方式：
    python -m apps.web.server
浏览器打开 http://127.0.0.1:8765
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apps.web.library_resolver import Triple, identify_candidates
from polarscan.api import Polarscan
from polarscan.core.index import Asset, Polaroid


# ============================================================
# 配置：data_dir 存放索引与缩略图，默认与代码位于同一块 SSD
# 原始 PNG 的绝对路径保存在 _index.yaml 中，运行时不需要 LIBRARY_ROOT
# ============================================================
DATA_DIR = Path(__file__).resolve().parent.parent.parent  # = D:\Dev\Workspace\Polarscan
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


# ============================================================
# 单例
# ============================================================
ps = Polarscan(DATA_DIR)
app = FastAPI(title="Polarscan")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================
# Jinja 过滤器：纯函数，不写 YAML、不调用 API，只在渲染时派生字符串
# ============================================================
import re as _re
from datetime import date as _date, timedelta as _td

def _id_date_range(pid: str) -> list[str]:
    """从 polaroid id 解析出拍摄日期范围, 展开为 [YYYY-MM-DD, ...] 列表.

    - '2026-07-25-26--img...'  → ['2026-07-25', '2026-07-26']
    - '2026-05-01-04--img...'  → ['2026-05-01', '2026-05-02', '2026-05-03', '2026-05-04']
    - '2026-07-25--img...'      → ['2026-07-25']
    - 'dandan_xxx' (手命名)    → []
    """
    if not pid:
        return []
    m = _re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:-(\d{2}))?--', pid)
    if not m:
        return []
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    end_day = int(m.group(4)) if m.group(4) else d
    if end_day < d:
        # 跨月范围（例如 '2026-01-31-02-01'）不展开，留给用户手动填写
        return []
    try:
        start = _date(y, mo, d)
    except ValueError:
        return []
    out = []
    cur = start
    for _ in range(end_day - d + 1):
        out.append(cur.isoformat())
        cur = cur + _td(days=1)
    return out


def _shot_date_hint(pid: str) -> str:
    """返回单日推荐值；日期范围取首日，供列表卡片在字段为空时回退显示。"""
    rng = _id_date_range(pid)
    return rng[0] if rng else ''


templates.env.filters['id_date_range'] = _id_date_range
templates.env.filters['shot_date_hint'] = _shot_date_hint


def reload_ps() -> None:
    ps.reload()


# ============================================================
# 工作台主界面
# ============================================================
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    polaroids = ps.polaroids()
    if polaroids:
        return RedirectResponse(f"/bench/{polaroids[0].id}", status_code=303)
    return RedirectResponse("/list", status_code=303)


@app.get("/list", response_class=HTMLResponse)
def list_view(request: Request, tag: Optional[str] = None):
    items = ps.polaroids()
    if tag:
        items = [p for p in items if tag in p.tags]
    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "polaroids": items,
            "tag_filter": tag,
            "all_count": len(ps.polaroids()),
        },
    )


def _bench_ctx(p: Polaroid):
    # 工作台只接收当前拍立得与全表导航信息。
    # 日期段内导航由前端负责：列表页把全部 id 缓存到 localStorage，工作台再读取。
    # 后端不按 id 前缀切分日期段；shot_date 由用户手动填写，不在这里派生。
    polaroids = ps.polaroids()
    idx = ps.polaroid_index_of(p.id)
    # assets 是 Asset dataclass 列表, Jinja tojson 不能直接序列化; 预先 dict + json.
    # 给前端 modal 用, 编辑后整体替换.
    assets_json = json.dumps([asdict(a) for a in p.assets])
    return {
        "p": p,
        "idx": idx,
        "total": len(polaroids),
        "prev_id": ps.prev_polaroid(p.id).id if ps.prev_polaroid(p.id) else None,
        "next_id": ps.next_polaroid(p.id).id if ps.next_polaroid(p.id) else None,
        "next_untagged_id": ps.next_untagged(p.id).id if ps.next_untagged(p.id) else None,
        "char_values": ps.all_tags_with_prefix("char"),
        "event_values": ps.all_tags_with_prefix("event"),
        "theme_values": ps.all_tags_with_prefix("theme"),
        "collection_values": ps.all_tags_with_prefix("collection"),
        "composite_values": ps.all_tags_with_prefix("composite"),
        "moment_values": ps.all_tags_with_prefix("moment"),
        "shot_values": ps.all_tags_with_prefix("shot"),
        "sig_values": ps.all_tags_with_prefix("sig"),
        "assets_json": assets_json,
    }


@app.get("/bench/{pid}", response_class=HTMLResponse)
def bench(request: Request, pid: str):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, f"未找到拍立得：{pid}")
    return templates.TemplateResponse(request, "bench.html", _bench_ctx(p))


@app.post("/bench/{pid}/autosave")
async def bench_autosave(
    pid: str,
    shot_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    """自动保存端点：只更新请求中实际传入的字段。

    用于前端自动保存标签增减，以及 `shot_date` 和 `notes` 输入框的防抖更新。
    返回 `ok`、`tags`、`shot_date` 与 `notes_len`，供界面展示保存状态。
    """
    from fastapi.responses import JSONResponse

    p = ps.polaroid(pid)
    if p is None:
        return JSONResponse({"ok": False, "error": "未找到拍立得"}, status_code=404)

    if tags is not None:
        p.tags = [t.strip() for t in tags.split(",") if t.strip()]
    if shot_date is not None:
        p.shot_date = shot_date.strip() or None
    if notes is not None:
        p.notes = notes

    ps.upsert_polaroid(p)
    ps.save()
    return JSONResponse({
        "ok": True,
        "tags": p.tags,
        "shot_date": p.shot_date,
        "notes_len": len(p.notes),
    })


@app.post("/bench/{pid}")
async def bench_save(
    pid: str,
    shot_date: str = Form(""),
    notes: str = Form(""),
    tags: str = Form(""),
):
    """保留整张表单提交路径；默认由自动保存接管。

    此端点主要供未启用 JavaScript 时的 HTML 表单回退使用。
    """
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, "未找到拍立得")
    new_tags = [t.strip() for t in tags.split(",") if t.strip()]
    p.tags = new_tags
    p.shot_date = shot_date.strip() or None
    p.notes = notes
    ps.upsert_polaroid(p)
    ps.save()
    return RedirectResponse(f"/bench/{pid}", status_code=303)


@app.post("/bench/{pid}/delete")
async def bench_delete(pid: str):
    if not ps.delete_polaroid(pid):
        raise HTTPException(404, "未找到拍立得")
    ps.save()
    # 删除后跳转到下一张、上一张或列表
    next_p = ps.next_polaroid(pid)
    if next_p is not None:
        return RedirectResponse(f"/bench/{next_p.id}", status_code=303)
    prev_p = ps.prev_polaroid(pid)
    if prev_p is not None:
        return RedirectResponse(f"/bench/{prev_p.id}", status_code=303)
    return RedirectResponse("/list", status_code=303)


@app.get("/bench/{pid}/goto/{direction}")
def bench_goto(pid: str, direction: str):
    if direction == "prev":
        target = ps.prev_polaroid(pid)
    elif direction == "next":
        target = ps.next_polaroid(pid)
    elif direction == "untagged":
        target = ps.next_untagged(pid)
    else:
        raise HTTPException(400, "导航方向必须是 prev、next 或 untagged")
    if target is None:
        return RedirectResponse(f"/bench/{pid}", status_code=303)
    return RedirectResponse(f"/bench/{target.id}", status_code=303)


# ============================================================
# 新建：显式创建表单，并自动派生 id
# ============================================================
@app.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    shot_date: Optional[str] = None,
    primary_char: Optional[str] = None,
    asset: Optional[str] = None,
):
    suggested = ps.suggest_id(shot_date, [f"char:{primary_char}"] if primary_char else [])
    return templates.TemplateResponse(
        request,
        "new.html",
        {
            "error": None,
            "default_pid": suggested,
            "default_asset": asset or "",
            "default_shot_date": shot_date or "",
            "default_primary_char": primary_char or "",
            "char_values": ps.all_tags_with_prefix("char"),
        },
    )


@app.post("/new")
async def new_create(
    request: Request,
    pid: str = Form(...),
    asset_path: str = Form(...),
    tags: str = Form(""),
    shot_date: str = Form(""),
    notes: str = Form(""),
):
    if ps.polaroid(pid):
        return templates.TemplateResponse(
            request,
            "new.html",
            {
                "error": f"id '{pid}' 已存在，请修改后重试（也可直接编辑 YAML）",
                "default_pid": pid,
                "default_asset": asset_path,
                "default_shot_date": shot_date,
                "char_values": ps.all_tags_with_prefix("char"),
            },
            status_code=400,
        )
    p = Polaroid(
        id=pid.strip(),
        shot_date=shot_date.strip() or None,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        notes=notes,
    )
    if asset_path.strip():
        p.assets.append(Asset(role="front", path=asset_path.strip()))
    ps.upsert_polaroid(p)
    ps.save()
    return RedirectResponse(f"/bench/{p.id}", status_code=303)


# ============================================================
# 标签池管理：列出指定前缀的标签，并编辑单个标签的元数据
# ============================================================
@app.get("/pool/{prefix}", response_class=HTMLResponse)
def pool_index(request: Request, prefix: str):
    items = ps.all_tags_in_pool(prefix)
    # 同时统计标签使用数量；先按使用频率降序，同频次再按键名字母序升序
    enriched = []
    for k, meta in items.items():
        count = len(ps.polaroids_with_tag(prefix, k))
        enriched.append({"key": k, "meta": meta, "count": count})
    enriched.sort(key=lambda x: (-x["count"], x["key"]))
    return templates.TemplateResponse(
        request,
        "pool_index.html",
        {
            "prefix": prefix,
            "items": enriched,
        },
    )


@app.get("/pool/{prefix}/{key}/edit", response_class=HTMLResponse)
def pool_edit_form(
    request: Request,
    prefix: str,
    key: str,
    return_to: Optional[str] = None,
):
    info = ps.tag_info(prefix, key)
    used_by = ps.polaroids_with_tag(prefix, key)
    return templates.TemplateResponse(
        request,
        "pool_edit.html",
        {
            "prefix": prefix,
            "key": key,
            "info": info,
            "used_by": used_by,
            "return_to": return_to or "/pool/" + prefix,
        },
    )


@app.post("/pool/{prefix}/{key}/edit")
async def pool_edit_save(
    prefix: str,
    key: str,
    canonical_name: str = Form(""),
    aliases: str = Form(""),
    notes: str = Form(""),
    extra_json: str = Form(""),
    return_to: Optional[str] = Form(None),
):
    # 表单全量提交：主字段采用全量覆盖语义，空字符串或空列表表示清空
    # 以旧数据为基础，保证只修改一个字段时其他字段不会丢失
    info: dict = dict(ps.tag_info(prefix, key))
    info["canonical_name"] = canonical_name.strip()
    info["aliases"] = [a.strip() for a in aliases.split(",") if a.strip()]
    info["notes"] = notes.strip()
    # 额外字段（date、venue、year、label、parts_count 等）采用 JSON 合并语义
    # 只有用户传入 JSON 时才修改，否则保留原有额外字段
    if extra_json.strip():
        try:
            extras = json.loads(extra_json)
            if isinstance(extras, dict):
                info.update(extras)
        except json.JSONDecodeError:
            pass
    ps.set_tag_info(prefix, key, info)
    ps.save()
    target = return_to or f"/pool/{prefix}"
    return RedirectResponse(target, status_code=303)


@app.post("/pool/{prefix}/{key}/delete")
async def pool_delete(prefix: str, key: str):
    ps.delete_tag(prefix, key)
    ps.save()
    return RedirectResponse(f"/pool/{prefix}", status_code=303)


# ============================================================
# 图片
# ============================================================
@app.get("/thumb/{pid}")
def thumb(pid: str):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, "未找到拍立得")
    tp = ps.thumb_path_for(p, asset_idx=0)
    if tp is None or not tp.exists():
        raise HTTPException(404, "未找到缩略图（资产缺失或无法读取）")
    return FileResponse(tp)


@app.get("/thumb/{pid}/{asset_idx:int}")
def thumb_idx(pid: str, asset_idx: int):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, "未找到拍立得")
    tp = ps.thumb_path_for(p, asset_idx=asset_idx)
    if tp is None or not tp.exists():
        raise HTTPException(404, "未找到缩略图")
    return FileResponse(tp)


@app.get("/img/{pid}")
def img(pid: str):
    """仅在用户从工作台主动点击“查看原图”时读取 F 盘原图。"""
    p = ps.polaroid(pid)
    if p is None or not p.assets:
        raise HTTPException(404, "未找到资产")
    return _serve_asset(p.assets[0].path)


@app.get("/img/{pid}/{asset_idx:int}")
def img_idx(pid: str, asset_idx: int):
    p = ps.polaroid(pid)
    if p is None or not p.assets or asset_idx < 0 or asset_idx >= len(p.assets):
        raise HTTPException(404, "未找到资产")
    return _serve_asset(p.assets[asset_idx].path)


def _serve_asset(asset_path: str):
    src = Path(asset_path)
    if not src.exists():
        raise HTTPException(404, "资产文件不存在")
    return FileResponse(src)


@app.post("/reload")
def reload_endpoint():
    reload_ps()
    return RedirectResponse("/", status_code=303)


# ============================================================
# drop 工作流：浏览器拖入文件时的 identify 端点
# ============================================================
@app.post("/api/drop/identify")
async def api_drop_identify(request: Request):
    """drop 工作流的 identify 端点（零 F:盘读 IO）。

    输入：浏览器给的 File 元数据 (name/size/lastModified) + 客户端 blake2b hash。
    输出：
      - by_hash: 已索引中 hash 命中的 [(pid, asset_idx), ...]
      - candidates: F:盘 (name+size+mtime) 三元组命中的路径 + 是否已在 yaml

    library_root 未配置时 candidates 为空列表。
    hash 为空字符串时 by_hash 为空列表（hash 校验跳过，仅靠路径候选）。
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "请求体必须是合法 JSON")

    name = body.get("name")
    size = body.get("size")
    last_modified_ms = body.get("lastModified_ms")
    h = body.get("hash") or ""

    if not isinstance(name, str) or not name:
        raise HTTPException(400, "缺少 name（字符串）")
    if not isinstance(size, (int, float)):
        raise HTTPException(400, "缺少 size（数字）")
    if not isinstance(last_modified_ms, (int, float)):
        raise HTTPException(400, "缺少 lastModified_ms（数字）")

    # 1) hash 反向查
    by_hash = [
        {"pid": pid, "asset_idx": idx}
        for pid, idx in ps.find_by_hash(h)
    ]

    # 2) 路径候选 + 是否已在 yaml
    candidates: list[dict[str, Any]] = []
    library_root = ps.library_root
    if library_root:
        qt = Triple(
            name=name,
            size=int(size),
            mtime=round(last_modified_ms / 1000.0),
        )
        result = identify_candidates(library_root, [qt])
        for cand in result.get(qt, []):
            path_str = str(cand.path)
            in_yaml_hits = ps.find_by_path(path_str)
            in_yaml_pid = in_yaml_hits[0][0] if in_yaml_hits else None
            candidates.append({"path": path_str, "in_yaml_pid": in_yaml_pid})

    return {"by_hash": by_hash, "candidates": candidates}


# ============================================================
# drop 工作流: 创建 / 追加 / 编辑 polaroid
# ============================================================
@app.post("/api/polaroids/import-from-files")
async def api_import_from_files(request: Request):
    """drop 工作流的确认导入入口: 从 F:盘路径集合创建新 polaroid。

    请求体 (JSON):
      {
        pid: str,
        path: [str, ...],         # F:盘绝对路径
        role: [str, ...] | null,   # 可选, 与 path 等长; 默认 front/back/additional
        date: str | null,          # shot_date
        char: str | null,          # 用于派生 id (与 date 一起)
        tags: [str, ...],          # 直接写入
        notes: str                 # 直接写入
      }

    返回: {pid: "..."}
    错误:
      - 400: 请求体非法 / 字段缺失
      - 409: pid 已存在 / 读取文件失败
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "请求体必须是合法 JSON")

    pid = body.get("pid")
    paths = body.get("path") or []
    roles = body.get("role")
    date = body.get("date")
    char = body.get("char")
    tags = body.get("tags") or []
    notes = body.get("notes") or ""

    if not isinstance(pid, str) or not pid:
        raise HTTPException(400, "缺少 pid（字符串）")
    if not isinstance(paths, list) or not paths:
        raise HTTPException(400, "缺少 path（非空列表）")
    if roles is not None and not isinstance(roles, list):
        raise HTTPException(400, "role 必须是列表或 null")
    if not isinstance(tags, list):
        raise HTTPException(400, "tags 必须是列表")

    try:
        polaroid = ps.import_from_files(
            paths=paths,
            roles=roles,
            date=date,
            char=char,
            tags=tags,
            notes=notes,
            pid=pid,
        )
    except ValueError as e:
        # pid 冲突或 paths/roles 数量不符
        msg = str(e)
        if "已存在" in msg:
            raise HTTPException(409, msg)
        raise HTTPException(400, msg)
    except OSError as e:
        # 读取 F:盘文件失败
        raise HTTPException(409, f"读取文件失败: {e}")

    return {"pid": polaroid.id}


@app.post("/api/polaroids/{pid}/append-files")
async def api_append_files(pid: str, request: Request):
    """把 F:盘路径集合追加到现有 polaroid。

    请求体 (JSON): { path: [str, ...], role: [str, ...] | null }
    返回: {pid: "...", asset_count: N}
    """
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


@app.post("/bench/{pid}/save-assets")
async def bench_save_assets(pid: str, request: Request):
    """原子替换 polaroid 的 assets 列表 (modal 编辑入口)。

    请求体 (JSON): { assets: [{role, path, captured_at, device}, ...] }
    约束: assets 里的 path 集合必须 ⊆ 当前 polaroid 的 path 集合。
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "请求体必须是合法 JSON")

    assets = body.get("assets")
    if not isinstance(assets, list) or not assets:
        raise HTTPException(400, "缺少 assets（非空列表）")

    try:
        polaroid = ps.save_assets(pid, assets)
    except ValueError as e:
        msg = str(e)
        if "未找到" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)

    return {"pid": polaroid.id, "asset_count": len(polaroid.assets)}


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
