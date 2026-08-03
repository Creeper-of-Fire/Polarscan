"""End-to-end: 完整 path, 包括新建/编辑/缩略图. 会修改 _index.yaml, 用完会回滚."""
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from apps.web.server import app, ps as server_ps, LIBRARY_ROOT

# 备份 _index.yaml 避免污染用户数据
LIB = Path(LIBRARY_ROOT)
INDEX_FILE = LIB / "_index.yaml"
BAK_FILE = LIB / "_index.yaml.bak"
shutil.copy(INDEX_FILE, BAK_FILE)

try:
    client = TestClient(app)

    print("--- POST /new 创建 polaroid ---")
    r = client.post("/new", data={
        "pid": "smoke_test_001",
        "asset_path": "2026.07.18/img20260720_19253733.png",
        "tags": "event:shenshan_3rd_om_cd, char:strawberry, char:hime, shot:pair",
        "shot_date": "2026-07-18",
        "notes": "smoke test entry, will be removed",
    }, follow_redirects=False)
    print(f"  status={r.status_code} location={r.headers.get('location')}")
    assert r.status_code == 303

    print("--- GET /polaroid/smoke_test_001 ---")
    r = client.get("/polaroid/smoke_test_001")
    print(f"  status={r.status_code} bytes={len(r.text)}")
    assert r.status_code == 200
    assert "smoke_test_001" in r.text
    assert "山海誓约" in r.text or "shenshan" in r.text

    print("--- GET /thumb/smoke_test_001 (生成缩略图) ---")
    r = client.get("/thumb/smoke_test_001")
    print(f"  status={r.status_code} bytes={len(r.content)} content-type={r.headers.get('content-type')}")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/")

    print("--- GET / 列表中能查到 ---")
    r = client.get("/")
    assert "smoke_test_001" in r.text
    print("  ✓ smoke_test_001 in index")

    print("--- POST /polaroid/{pid} 修改 tags ---")
    r = client.post("/polaroid/smoke_test_001", data={
        "tags": "event:shenshan_3rd_om_cd, char:strawberry, shot:solo",
        "shot_date": "2026-07-18",
        "notes": "edited",
    }, follow_redirects=False)
    print(f"  status={r.status_code}")
    assert r.status_code == 303
    r = client.get("/polaroid/smoke_test_001")
    assert "shot:solo" in r.text
    assert "char:hime" not in r.text
    print("  ✓ tags changed: hime removed, shot=solo")

    print("--- 删除清理 ---")
    r = client.post("/polaroid/smoke_test_001/delete", follow_redirects=False)
    assert r.status_code == 303

    r = client.get("/polaroid/smoke_test_001")
    assert r.status_code == 404
    print("  ✓ polaroid removed")

    print()
    print("E2E OK")

finally:
    if BAK_FILE.exists():
        shutil.move(BAK_FILE, INDEX_FILE)
        print("(restored _index.yaml from backup)")
    # 删除测试生成的 thumb 缓存
    t = LIB / ".thumbs" / "smoke_test_001.jpg"
    if t.exists():
        t.unlink()
