"""Visual dump: print key sections of bench HTML."""
import re
from fastapi.testclient import TestClient
import apps.web.server as srv

client = TestClient(srv.app)
r = client.get("/bench/dandan_2025_10_18_111")
text = r.text

m = re.search(r"<header>.*?</header>", text, re.S)
print("--- header ---")
print(m.group(0) if m else "NOT FOUND")
print()

m = re.search(r'<div class="bench-top">.*?</div>\s*<div class="bench-layout">', text, re.S)
print("--- bench-top (first 1500 chars) ---")
if m:
    print(m.group(0)[:1500])
print()

m = re.search(r'<div class="chip-stream"[\s\S]*?</div>\s*<div class="tag-input-row">', text)
print("--- chip-stream (first 1200 chars) ---")
if m:
    print(m.group(0)[:1200])
print()

# Count checkboxes, buttons
print(f"buttons: {text.count('<button')}")
print(f"inputs:  {text.count('<input')}")
print(f"chips:   {text.count('class=\"chip chip-')}")
