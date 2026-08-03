"""Local web app: bench GUI + tag-pool CRUD.

启动:
    python -m apps.web.server
浏览器打开 http://127.0.0.1:8765
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from polarscan.api import Polarscan
from polarscan.core.index import Asset, Polaroid


# ============================================================
# 配置
# ============================================================
LIBRARY_ROOT = Path(r"F:\相册\偶活\拍立得扫描\偶活拍立得扫描").resolve()
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


# ============================================================
# 单例
# ============================================================
ps = Polarscan(LIBRARY_ROOT)
app = FastAPI(title="Polarscan")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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


@app.post("/bench/{pid}")
async def bench_save(
    pid: str,
    shot_date: str = Form(""),
    notes: str = Form(""),
    tags: str = Form(""),
    focus: Optional[str] = Form(None),
):
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
    # 附: 哪些 polaroid 带某个 tag
    enriched = []
    for k, meta in sorted(items.items()):
        count = len(ps.polaroids_with_tag(prefix, k))
        enriched.append({"key": k, "meta": meta, "count": count})
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
    info: dict = {}
    if canonical_name.strip():
        info["canonical_name"] = canonical_name.strip()
    if aliases.strip():
        info["aliases"] = [a.strip() for a in aliases.split(",") if a.strip()]
    if notes.strip():
        info["notes"] = notes
    # extra 字段 (date / venue / year / label / parts_count / 等) — 解析 JSON
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
    tp = ps.thumb_path_for(p)
    if tp is None or not tp.exists():
        raise HTTPException(404, "no thumb (asset missing or unreadable)")
    return FileResponse(tp)


@app.get("/img/{pid}")
def img(pid: str):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, "not found")
    src = ps.first_asset_path(p)
    if src is None or not src.exists():
        raise HTTPException(404, "no asset")
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
