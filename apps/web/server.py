"""Local web app for browsing + editing polaroids.

Runs on 127.0.0.1:8765 by default. Reads/writes _index.yaml under LIBRARY_ROOT.

启动：
    python -m apps.web.server
然后浏览器打开 http://127.0.0.1:8765
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from polarscan.api import Polarscan
from polarscan.core.index import Asset, Polaroid


# ============================================================
# 数据路径配置: 用户改这里就能换数据源
# ============================================================
LIBRARY_ROOT = Path(r"F:\相册\偶活\拍立得扫描\偶活拍立得扫描").resolve()

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


# ============================================================
# 单例 Polarscan（每次请求都 reload 不如启动期一次加载）
# ============================================================
ps = Polarscan(LIBRARY_ROOT)

app = FastAPI(title="Polarscan")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def reload_ps() -> None:
    """Force reload from disk (in case other tools edited _index.yaml)."""
    ps.reload()


# ============================================================
# 视图路由
# ============================================================
@app.get("/", response_class=HTMLResponse)
def index(request: Request, tag: Optional[str] = None):
    items = ps.polaroids()
    if tag:
        items = [p for p in items if tag in p.tags]
    items.sort(key=lambda p: (p.shot_date or "9999", p.id))
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "polaroids": items,
            "tag_filter": tag,
            "all_count": len(ps.polaroids()),
        },
    )


@app.get("/polaroid/{pid}", response_class=HTMLResponse)
def polaroid_detail(request: Request, pid: str):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, f"polaroid '{pid}' not found")
    return templates.TemplateResponse(
        request,
        "polaroid.html",
        {
            "p": p,
            "char_tags": ps.all_tags_with_prefix("char"),
            "event_tags": ps.all_tags_with_prefix("event"),
            "theme_tags": ps.all_tags_with_prefix("theme"),
            "collection_tags": ps.all_tags_with_prefix("collection"),
            "composite_tags": ps.all_tags_with_prefix("composite"),
            "moment_tags": ps.all_tags_with_prefix("moment"),
            "char_metadata": ps.tag_metadata("char"),
        },
    )


@app.post("/polaroid/{pid}")
async def polaroid_save(
    pid: str,
    tags: str = Form(""),
    shot_date: str = Form(""),
    notes: str = Form(""),
):
    p = ps.polaroid(pid)
    if p is None:
        raise HTTPException(404, "not found")
    p.tags = [t.strip() for t in tags.split(",") if t.strip()]
    p.shot_date = shot_date.strip() or None
    p.notes = notes
    ps.upsert_polaroid(p)
    ps.save()
    return RedirectResponse(f"/polaroid/{pid}", status_code=303)


@app.get("/new", response_class=HTMLResponse)
def polaroid_new_form(request: Request, pid: Optional[str] = None, asset: Optional[str] = None):
    return templates.TemplateResponse(
        request,
        "new.html",
        {
            "error": None,
            "default_pid": pid or "",
            "default_asset": asset or "",
        },
    )


@app.post("/new")
async def polaroid_create(
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
                "error": f"id '{pid}' 已存在",
                "default_pid": pid,
                "default_asset": asset_path,
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
    return RedirectResponse(f"/polaroid/{p.id}", status_code=303)


@app.post("/polaroid/{pid}/delete")
async def polaroid_delete(pid: str):
    ps.delete_polaroid(pid)
    ps.save()
    return RedirectResponse("/", status_code=303)


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
    """原始图只在被点开时按需读."""
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
