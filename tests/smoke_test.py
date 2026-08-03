"""Smoke test: hit every endpoint and confirm 200/expected."""
from fastapi.testclient import TestClient
from apps.web.server import app

client = TestClient(app)

print("--- GET / ---")
r = client.get("/")
print(f"  status={r.status_code} bytes={len(r.text)}")
assert r.status_code == 200
assert "Polarscan" in r.text
assert "还没有" in r.text

print("--- GET /new ---")
r = client.get("/new")
print(f"  status={r.status_code} bytes={len(r.text)}")
assert r.status_code == 200

print("--- GET /polaroid/nonexistent ---")
r = client.get("/polaroid/nonexistent_id")
print(f"  status={r.status_code}")
assert r.status_code == 404

print("--- GET /static/app.css ---")
r = client.get("/static/app.css")
print(f"  status={r.status_code} bytes={len(r.text)}")
assert r.status_code == 200
assert len(r.text) > 1000

print()
print("ALL OK")
