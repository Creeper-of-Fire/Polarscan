"""Local web app: bench GUI + tag-pool CRUD.

启动:
    python -m apps.web.server
浏览器打开 http://127.0.0.1:8765
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from polarscan.api import Polarscan
from polarscan.core.index import Asset, Polaroid


# ============================================================
# 配置: data_dir (派生: 索引 + 缩略图, 跟代码同盘 SSD)
#         原 PNG 的绝对路径存在 _index.yaml 里, 运行时不需要 LIBRARY_ROOT
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
# Jinja filters (纯函数, 不写 yaml, 不调 API — 只在渲染时做字符串派生)
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
        # 跨月范围 (e.g. '2026-01-31-02-01') — 不展开, 留给手填
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
    """单日推荐值 (范围取首日). 给 list 卡片 fallback 用."""
    rng = _id_date_range(pid)
    return rng[0] if rng else ''


templates.env.filters['id_date_range'] = _id_date_range
templates.env.filters['shot_date_hint'] = _shot_date_hint


def reload_ps() -> None:
    ps.reload()


# ============================================================
# 工作台 (主 GUI)
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


def _bench_ctx(request: Request, p: Polaroid, focus_tag: str | None = None):
    # bench ctx 只发当前 polaroid + 全表 nav (prev/next/next_untagged).
    # 段内导航 (本段: 2026-07-25-26 / 该段第一张/最后一张) 是前端的事:
    #   list 页面把全表 id 缓存到 localStorage, bench 页面从 localStorage 读.
    # 后端不做"按 id-prefix 分日期段"的活; shot_date 字段是用户手填的, 不做派生.
    polaroids = ps.polaroids()
    idx = ps.polaroid_index_of(p.id)
    return {
        "p": p,
        "polaroids": polaroids,
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
        "suggested_id": ps.suggest_id(p.shot_date, p.tags),
        "focus_tag": focus_tag,
    }


@app.get("/bench/{pid}", response_class=HTMLResponse)
def bench(request: Request, pid: str, focus: Optional[str] = None):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, f"polaroid '{pid}' not found")
    return templates.TemplateResponse(request, "bench.html", _bench_ctx(request, p, focus_tag=focus))


@app.post("/bench/{pid}/autosave")
async def bench_autosave(
    pid: str,
    shot_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    """JSON 端点: 改了什么传什么, 没传的不动.

    用于 JS autosave (tag chip 增减 + shot_date / notes 的 input 防抖).
    返回 {ok: True, tags_count: ..., shot_date: ..., notes_len: ...} 用于状态展示.
    """
    from fastapi.responses import JSONResponse

    p = ps.polaroid(pid)
    if p is None:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)

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
    focus: Optional[str] = Form(None),
):
    """保留 'submit 整个表单' 路径. 默认 autosave 已接管, 此 endpoint 主要供
    HTML form 回退 (无 JS 时)."""
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, "not found")
    new_tags = [t.strip() for t in tags.split(",") if t.strip()]
    p.tags = new_tags
    p.shot_date = shot_date.strip() or None
    p.notes = notes
    ps.upsert_polaroid(p)
    ps.save()
    if focus:
        return RedirectResponse(f"/bench/{pid}?focus={focus}", status_code=303)
    return RedirectResponse(f"/bench/{pid}", status_code=303)


@app.post("/bench/{pid}/delete")
async def bench_delete(pid: str):
    if not ps.delete_polaroid(pid):
        raise HTTPException(404, "not found")
    ps.save()
    # 删完跳到下一张 / 上一张 / 列表
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
        raise HTTPException(400, "direction must be prev|next|untagged")
    if target is None:
        return RedirectResponse(f"/bench/{pid}", status_code=303)
    return RedirectResponse(f"/bench/{target.id}", status_code=303)


# ============================================================
# 新建 (显式创建表单, 带 id 自动派生)
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
                "error": f"id '{pid}' 已存在, 改一个再试 (或直接改 yaml)",
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
# 池管理: 列出 prefix 下的所有 tag + 编辑某个 tag 的元数据
# ============================================================
@app.get("/pool/{prefix}", response_class=HTMLResponse)
def pool_index(request: Request, prefix: str):
    items = ps.all_tags_in_pool(prefix)
    # 附: 哪些 polaroid 带某个 tag; 按使用频率降序, 同频次按 key 字母升序
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
    # 表单全量提交 → 主字段全量覆盖语义: 空字符串/空列表 = 清空, 不再做 trim 判空跳过
    # 用旧 info 做 base, 保证只改一个字段时其他字段不消失
    info: dict = dict(ps.tag_info(prefix, key))
    info["canonical_name"] = canonical_name.strip()
    info["aliases"] = [a.strip() for a in aliases.split(",") if a.strip()]
    info["notes"] = notes.strip()
    # extra 字段 (date / venue / year / label / parts_count / 等) — JSON merge 语义
    # (跟主字段的"赋值"语义不同, 保留: 用户传 JSON 才动, 否则保留原 extras)
    if extra_json.strip():
        import json
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
        raise HTTPException(404, "not found")
    tp = ps.thumb_path_for(p, asset_idx=0)
    if tp is None or not tp.exists():
        raise HTTPException(404, "no thumb (asset missing or unreadable)")
    return FileResponse(tp)


@app.get("/thumb/{pid}/{asset_idx:int}")
def thumb_idx(pid: str, asset_idx: int):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, "not found")
    tp = ps.thumb_path_for(p, asset_idx=asset_idx)
    if tp is None or not tp.exists():
        raise HTTPException(404, "no thumb")
    return FileResponse(tp)


@app.get("/img/{pid}")
def img(pid: str):
    """原图: 用户在 bench 页面主动点 '查看原图' 才触发, 直接读 F 盘."""
    p = ps.polaroid(pid)
    if p is None or not p.assets:
        raise HTTPException(404, "no asset")
    return _serve_asset(p.assets[0].path)


@app.get("/img/{pid}/{asset_idx:int}")
def img_idx(pid: str, asset_idx: int):
    p = ps.polaroid(pid)
    if p is None or not p.assets or asset_idx < 0 or asset_idx >= len(p.assets):
        raise HTTPException(404, "no asset")
    return _serve_asset(p.assets[asset_idx].path)


def _serve_asset(asset_path: str):
    src = Path(asset_path)
    if not src.exists():
        raise HTTPException(404, "asset missing on F drive")
    return FileResponse(src)


@app.post("/reload")
def reload_endpoint():
    reload_ps()
    return RedirectResponse("/", status_code=303)


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
