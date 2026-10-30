"""Seed the catalog from the Drive index into the database.

Usage
-----
Local SQLite (default):
    python scripts/import_drive.py

Remote somee.com MSSQL:
    python scripts/import_drive.py --remote

The ``--remote`` flag forces the script to use the MSSQL connection
configured in ``.env`` (via DATABASE_URL or the four DB_* variables).
Without the flag, the script always targets local SQLite — even if
DATABASE_URL is set — so that a developer cannot accidentally write
14K rows into the shared cloud database.

Idempotent: re-running deletes old Drive-sourced rows before re-inserting.
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from flask import Flask

from courses import COURSE_MAP, SKIP_TOP_FOLDERS, TYPE_KEYWORDS
from db_config import resolve_database_url
from extensions import db
from models import HEBREW_TO_GREGORIAN, STATUS_APPROVED, Course, Material
from schema import ensure_schema
from seed import seed_catalog

INDEX = ROOT / "instance" / "drive_index.json"
STUDY_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".zip", ".rar", ".7z", ".mp4", ".mov", ".mkv"}
SKIP_EXTENSIONS = {
    ".c",
    ".h",
    ".cpp",
    ".java",
    ".py",
    ".js",
    ".class",
    ".o",
    ".exe",
    ".dll",
    ".json",
    ".md",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
    ".gitignore",
}

DEFAULT_REMOTE_LIMIT = 2000

_HEBREW_YEAR_RE = re.compile(r"(תשפ[א-ו]|תשע[ז-ט]|תשפ(?=[^א-ת]))")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed the catalog from the Drive index into the database.",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Target somee.com MSSQL instead of local SQLite",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of materials to insert. "
            f"Defaults to {DEFAULT_REMOTE_LIMIT} for --remote, unlimited for local."
        ),
    )
    return parser.parse_args()


def _sqlite_url(instance_path):
    return "sqlite:///" + os.path.join(instance_path, "campus_plus.db")


def create_app(remote):
    """Build a minimal Flask app wired to the right database."""
    flask_app = Flask(__name__, instance_path=str(ROOT / "instance"))
    os.makedirs(flask_app.instance_path, exist_ok=True)

    if remote:
        url = resolve_database_url(os.environ, flask_app.instance_path)
        if "sqlite" in url.lower():
            print(
                "ERROR: --remote requires MSSQL credentials.\n"
                "Set DATABASE_URL or DB_SERVER/DB_NAME/DB_USER/DB_PASSWORD in .env"
            )
            sys.exit(1)
        server = url.split("@")[-1].split("/")[0] if "@" in url else "remote"
        print(f"Target: remote MSSQL ({server})", flush=True)
    else:
        url = _sqlite_url(flask_app.instance_path)
        print("Target: local SQLite", flush=True)

    flask_app.config["SQLALCHEMY_DATABASE_URI"] = url
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)
    return flask_app


def normalize(name):
    value = html.unescape(name or "")
    return value.replace("׳", "'").replace("\u2019", "'").replace("`", "'").strip()


def is_study_file(item):
    name = item["name"].lower()
    suffix = Path(name).suffix.lower()
    if suffix in SKIP_EXTENSIONS:
        return False
    if suffix in STUDY_EXTENSIONS:
        return True
    blob = " ".join(item["path"]).lower()
    return any(keyword in blob for keywords, _ in TYPE_KEYWORDS for keyword in keywords)


def infer_type(parts):
    blob = " ".join(parts).lower()
    for keywords, material_type in TYPE_KEYWORDS:
        if any(keyword.lower() in blob for keyword in keywords):
            return material_type
    name = parts[-1].lower()
    if name.endswith((".ppt", ".pptx")):
        return "presentations"
    if name.endswith((".mp4", ".mov", ".mkv")):
        return "recordings"
    return "summaries"


def infer_year(parts):
    """Infer the academic year from folder path components.

    Tries Gregorian (20XX) first, then Hebrew academic years
    (e.g. תשפ"ד → 2024). Returns 0 for unknown.
    """
    blob = " ".join(parts)

    gregorian = [int(y) for y in re.findall(r"\b(20\d{2})\b", blob)]
    if gregorian:
        return gregorian[-1]

    cleaned = blob.replace('"', "").replace("׳", "").replace("'", "").replace("״", "")
    for match in _HEBREW_YEAR_RE.findall(cleaned):
        if match in HEBREW_TO_GREGORIAN:
            return HEBREW_TO_GREGORIAN[match]

    return 0


def infer_icon(name):
    lower = name.lower()
    if lower.endswith((".ppt", ".pptx")):
        return "slides"
    if lower.endswith((".mp4", ".mov", ".mkv", ".avi")):
        return "video"
    return "pdf"


def drive_url(item):
    if "/folders/" in item.get("url", ""):
        return ""
    if "docs.google.com" in item.get("url", ""):
        return item["url"].split("&")[0]
    return f"https://drive.google.com/file/d/{item['id']}/preview"


def seed_courses():
    """Migrate English→Hebrew course names and ensure all courses exist."""
    seed_catalog()


def remove_old_drive_rows():
    """Delete previously-seeded Drive rows so re-import is clean."""
    removed = Material.query.filter(
        Material.file_path.like("%drive.google.com%")
    ).delete(synchronize_session=False)
    Material.query.filter(
        Material.file_path.is_(None), Material.uploader_id.is_(None)
    ).delete(synchronize_session=False)
    db.session.commit()
    return removed


BATCH_SIZE = 100


def import_materials(files, limit):
    """Insert filtered Drive files as approved materials.

    Returns (added, skipped, unmatched_dict).
    """
    course_cache = {c.name: c.id for c in Course.query.all()}

    existing_urls = set(
        url
        for (url,) in db.session.query(Material.file_path)
        .filter(Material.file_path.isnot(None))
        .all()
    )

    added = 0
    skipped = 0
    unmatched = {}

    for item in files:
        if limit is not None and added >= limit:
            break

        item["name"] = normalize(item["name"])
        item["path"] = [normalize(part) for part in item["path"]]

        if not is_study_file(item):
            skipped += 1
            continue

        top = item["path"][0]
        if top in SKIP_TOP_FOLDERS:
            skipped += 1
            continue
        if top not in COURSE_MAP:
            unmatched[top] = unmatched.get(top, 0) + 1
            skipped += 1
            continue

        url = drive_url(item)
        if not url or url in existing_urls:
            continue

        course_id = course_cache[COURSE_MAP[top]]
        material_type = infer_type(item["path"])
        year = infer_year(item["path"])
        # Year 0 means the folder had no year. uploaded_at is the import day.
        material = Material(
            file_name=item["name"][:255],
            course_id=course_id,
            academic_year=year,
            material_type=material_type,
            icon_type=infer_icon(item["name"]),
            uploaded_at=date(year, 1, 1) if year else date.today(),
            status=STATUS_APPROVED,
            file_path=url,
            # ai_summary, confidence, ai_recommendation left as NULL:
            # NULL means "not evaluated", not "enqueue me".
            # The worker filters on status=pending, so these rows stay out.
        )
        db.session.add(material)
        existing_urls.add(url)
        added += 1

        if added % BATCH_SIZE == 0:
            db.session.flush()
            print(f"  ... {added} inserted so far", flush=True)

    db.session.commit()
    return added, skipped, unmatched


def print_summary(removed, added, skipped, unmatched, limit):
    if unmatched:
        print("unmatched tops:")
        for name, count in sorted(unmatched.items(), key=lambda item: -item[1]):
            print(f"  {count:4}  {name}")

    counts = dict(
        db.session.query(Course.name, db.func.count(Material.id))
        .join(Material)
        .filter(Material.status == STATUS_APPROVED)
        .group_by(Course.name)
        .all()
    )
    total = sum(counts.values())
    limit_note = f" (limit={limit})" if limit is not None else ""
    print(f"removed={removed}  added={added}  skipped={skipped}{limit_note}")
    print(f"courses_with_files={len(counts)}  total_approved={total}")
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]:
        print(f"  {count:4}  {name}")


def main():
    args = parse_args()
    limit = args.limit
    if limit is None and args.remote:
        limit = DEFAULT_REMOTE_LIMIT

    flask_app = create_app(args.remote)

    items = json.loads(INDEX.read_text(encoding="utf-8"))
    files = [item for item in items if item["kind"] == "file" and item.get("path")]
    print(f"Drive index: {len(items)} entries, {len(files)} files with paths", flush=True)

    with flask_app.app_context():
        db.create_all()
        ensure_schema()

        seed_courses()
        removed = remove_old_drive_rows()
        added, skipped, unmatched = import_materials(files, limit)
        print_summary(removed, added, skipped, unmatched, limit)


if __name__ == "__main__":
    main()
