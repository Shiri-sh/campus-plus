from pathlib import Path
import re

html = Path(__file__).resolve().parents[1].joinpath("instance/drive_root.html").read_text(encoding="utf-8")
# find file and doc links with nearby text
for pattern in [
    r"https://drive.google.com/file/d/[a-zA-Z0-9_-]+",
    r"https://docs.google.com/[^\"']+",
]:
    print(pattern, len(re.findall(pattern, html)))

# dump a file entry snippet
idx = html.find("/file/d/")
print("file snippet:", html[max(0, idx - 200) : idx + 400])
print("---")
# flip-entry
idx = html.find("flip-entry")
print("flip snippet:", html[idx : idx + 800] if idx >= 0 else "no flip-entry")
