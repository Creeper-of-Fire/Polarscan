"""Smoke test for new GUI bench + pool routes."""
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
import apps.web.server as srv
from apps.web.server import app, DATA_DIR

# backup _index.yaml (in DATA_DIR = D:\Dev\Workspace\Polarscan\)
DATA = Path(DATA_DIR)
INDEX_FILE = DATA / "_index.yaml"
BAK_FILE = DATA / "_index.yaml.bak"
shutil.copy(INDEX_FILE, BAK_FILE)

try:
    client = TestClient(app)

    # 1. root -> redirect
    r = client.get("/", follow_redirects=False)
    print(f"GET /:        {r.status_code} → {r.headers.get('location')}")
    assert r.status_code == 303

    # 2. bench
    r = client.get("/bench/dandan_2025_10_18_111")
    print(f"GET bench:    {r.status_code}, bytes={len(r.text)}")
    assert r.status_code == 200
    assert "dandan_2025_10_18_111" in r.text
    assert "tags" in r.text.lower()

    # 3. pool char
    r = client.get("/pool/char")
    print(f"GET pool/char: {r.status_code}, bytes={len(r.text)}")
    assert r.status_code == 200

    # 4. Save via POST /bench/{pid}
    r = client.post("/bench/dandan_2025_10_18_111", data={
        "tags": "char:my_push, shot:pair",
        "shot_date": "2025-10-18",
        "notes": "edited via smoke test",
    }, follow_redirects=False)
    print(f"POST bench save: {r.status_code} → {r.headers.get('location')}")
    assert r.status_code == 303

    srv.reload_ps()
    p = srv.ps.polaroid("dandan_2025_10_18_111")
    assert p is not None
    print(f"  after save tags: {p.tags}")
    print(f"  after save notes: {p.notes!r}")
    assert "char:my_push" in p.tags
    assert "shot:pair" in p.tags
    assert p.notes == "edited via smoke test"

    # 5. suggest id
    sid = srv.ps.suggest_id("2025-10-18", ["char:strawberry"])
    print(f"suggest_id: {sid}")
    assert sid.startswith("2025-10-18_strawberry_")

    # 6. pool_edit GET
    r = client.get("/pool/char/my_push/edit?return_to=/bench/dandan_2025_10_18_111")
    print(f"GET pool edit: {r.status_code}, bytes={len(r.text)}")
    assert r.status_code == 200
    assert "canonical_name" in r.text

    # 7. pool_edit POST
    r = client.post("/pool/char/my_push/edit", data={
        "canonical_name": "我的推",
        "aliases": "my_push, 我推, myoshi",
        "notes": "test alias",
        "extra_json": "",
        "return_to": "/bench/dandan_2025_10_18_111",
    }, follow_redirects=False)
    print(f"POST pool edit: {r.status_code} → {r.headers.get('location')}")
    assert r.status_code == 303

    srv.reload_ps()
    info = srv.ps.tag_info("char", "my_push")
    print(f"  pool info after save: {info}")
    assert info.get("canonical_name") == "我的推"
    assert "我推" in info.get("aliases", [])

    # 8. bench navigation: next/prev/untagged
    nxt = client.get("/bench/dandan_2025_10_18_111/goto/next", follow_redirects=False)
    print(f"GET next: {nxt.status_code} → {nxt.headers.get('location')}")
    assert nxt.status_code == 303
    nxt_un = client.get("/bench/dandan_2025_10_18_111/goto/untagged", follow_redirects=False)
    print(f"GET untagged: {nxt_un.status_code} → {nxt_un.headers.get('location')}")
    assert nxt_un.status_code == 303

    # 9. suggest_id derived from polaroid
    sid2 = srv.ps.suggest_id(p.shot_date, p.tags)
    print(f"suggest_id from current p: {sid2}")
    # current shot_date=2025-10-18, tags=[char:my_push, shot:pair]
    # primary char is my_push
    assert sid2.startswith("2025-10-18_my_push_")

    print()
    print("ALL OK")
finally:
    if BAK_FILE.exists():
        shutil.move(BAK_FILE, INDEX_FILE)
        print("(restored _index.yaml from backup)")
    # delete test thumb (in DATA_DIR)
    t = DATA / ".thumbs" / "dandan_2025_10_18_111.jpg"
    if t.exists():
        t.unlink()
