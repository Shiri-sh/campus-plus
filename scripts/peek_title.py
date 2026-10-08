from pathlib import Path
import re

html = Path(__file__).resolve().parents[1].joinpath("instance/drive_root.html").read_text(encoding="utf-8")
# grab a few complete flip-entry chunks
parts = html.split('class="flip-entry"')[1:4]
for part in parts:
    chunk = part[:1500]
    title = re.search(r'flip-entry-title[^>]*>([^<]+)', chunk)
    href = re.search(r'href="([^"]+)"', chunk)
    print("TITLE", title.group(1) if title else None)
    print("HREF", href.group(1) if href else None)
    print("---")
