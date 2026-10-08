import re
import urllib.request
from pathlib import Path

url = "https://drive.google.com/embeddedfolderview?id=1o_GJwTKUmR1GIPN9AH_L1X4suTstyuKO"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
out = Path(__file__).resolve().parents[1] / "instance" / "drive_root.html"
out.write_text(html, encoding="utf-8")
print("len", len(html))
print("folder hrefs", len(re.findall(r"/drive/folders/", html)))
print("file hrefs", len(re.findall(r"/file/d/", html)))
print("open id", len(re.findall(r"/open\?id=", html)))
print("data-id", len(re.findall(r"data-id=", html)))
print("uc?id", len(re.findall(r"uc\?id=", html)))
# print unique href patterns
hrefs = set(re.findall(r'href="([^"]+)"', html))
for href in sorted(hrefs)[:40]:
    print(href)
