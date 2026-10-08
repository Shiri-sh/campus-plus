import html as html_lib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_ID = "1o_GJwTKUmR1GIPN9AH_L1X4suTstyuKO"
OUT = Path(__file__).resolve().parents[1] / "instance" / "drive_index.json"
MAX_DEPTH = 4
SKIP_NAMES = {
    "main",
    "src",
    "node_modules",
    ".git",
    "old test",
    "__pycache__",
    "vendor",
    "bin",
    "obj",
    "dist",
    "build",
    "target",
    "cmake-build-debug",
}


def fetch(folder_id):
    url = f"https://drive.google.com/embeddedfolderview?id={folder_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return response.read().decode("utf-8", "replace")
    except Exception as error:
        print(f"skip {folder_id}: {error}", flush=True)
        return ""


def parse_entries(page):
    entries = []
    seen = set()
    for block in page.split('class="flip-entry"')[1:]:
        href_match = re.search(r'href="([^"]+)"', block)
        title_match = re.search(r"flip-entry-title[^>]*>([^<]+)", block)
        if not href_match or not title_match:
            continue
        name = html_lib.unescape(title_match.group(1)).strip()
        href = href_match.group(1)
        if "/folders/" in href:
            kind = "folder"
            item_id = re.search(r"/folders/([a-zA-Z0-9_-]+)", href).group(1)
        else:
            kind = "file"
            id_match = re.search(r"/(?:file|document|presentation|spreadsheets)/d/([a-zA-Z0-9_-]+)", href)
            if not id_match:
                continue
            item_id = id_match.group(1)
        if item_id in seen or not name:
            continue
        seen.add(item_id)
        entries.append({"id": item_id, "name": name, "kind": kind, "url": href})
    return entries


def walk(folder_id, path, seen_folders):
    if folder_id in seen_folders:
        return []
    seen_folders.add(folder_id)
    print(f"fetching {' / '.join(path) or 'ROOT'}...", flush=True)
    page = fetch(folder_id)
    entries = parse_entries(page)
    print(f"{' / '.join(path) or 'ROOT'}: {len(entries)} entries", flush=True)
    items = []
    for entry in entries:
        current_path = path + [entry["name"]]
        items.append({**entry, "path": current_path, "parent_id": folder_id})
        if entry["kind"] == "folder":
            if len(current_path) >= MAX_DEPTH:
                continue
            if entry["name"].strip().lower() in SKIP_NAMES:
                continue
            time.sleep(0.15)
            items.extend(walk(entry["id"], current_path, seen_folders))
    return items


def main():
    print("Listing Drive folder...", flush=True)
    items = walk(ROOT_ID, [], set())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    files = [item for item in items if item["kind"] == "file"]
    print(f"wrote {OUT}", flush=True)
    print(f"folders={sum(item['kind']=='folder' for item in items)} files={len(files)}", flush=True)


if __name__ == "__main__":
    main()
