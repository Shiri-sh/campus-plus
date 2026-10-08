import html
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app
from courses import COURSE_MAP, SKIP_TOP_FOLDERS, TYPE_KEYWORDS
from extensions import db
from models import STATUS_APPROVED, Course, Material

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


def normalize(name):
    value = html.unescape(name or "")
    return value.replace("׳", "'").replace("’", "'").replace("`", "'").strip()


def is_study_file(item):
    name = item["name"].lower()
    suffix = Path(name).suffix.lower()
    if suffix in SKIP_EXTENSIONS:
        return False
    if suffix in STUDY_EXTENSIONS:
        return True
    blob = " ".join(item["path"]).lower()
    return any(keyword in blob for keywords, _, _ in TYPE_KEYWORDS for keyword in keywords)


def infer_type(parts):
    blob = " ".join(parts).lower()
    for keywords, material_type, file_type in TYPE_KEYWORDS:
        if any(keyword.lower() in blob for keyword in keywords):
            return material_type, file_type
    name = parts[-1].lower()
    if name.endswith((".ppt", ".pptx")):
        return "presentations", "presentation"
    if name.endswith((".mp4", ".mov", ".mkv")):
        return "recordings", "recording"
    return "summaries", "summary"


def infer_year(parts):
    blob = " ".join(parts)
    years = [int(year) for year in re.findall(r"\b(20\d{2})\b", blob)]
    if years:
        return years[-1]
    return 2021


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


def main():
    items = json.loads(INDEX.read_text(encoding="utf-8"))
    files = [item for item in items if item["kind"] == "file" and item.get("path")]

    with app.app_context():
        for hebrew, english in COURSE_MAP.items():
            if not Course.query.filter_by(name=english).first():
                db.session.add(Course(name=english))
        db.session.commit()

        removed = Material.query.filter(Material.file_path.like("%drive.google.com%")).delete(
            synchronize_session=False
        )
        Material.query.filter(Material.file_path.is_(None), Material.uploader_id.is_(None)).delete(
            synchronize_session=False
        )
        db.session.commit()

        added = 0
        skipped = 0
        unmatched = {}
        for item in files:
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
            course = Course.query.filter_by(name=COURSE_MAP[top]).one()
            url = drive_url(item)
            if not url or Material.query.filter_by(file_path=url).first():
                continue
            material_type, file_type = infer_type(item["path"])
            material = Material(
                file_name=item["name"][:255],
                course_id=course.id,
                academic_year=infer_year(item["path"]),
                material_type=material_type,
                file_type=file_type,
                icon_type=infer_icon(item["name"]),
                uploaded_at=date(infer_year(item["path"]), 1, 1),
                status=STATUS_APPROVED,
                file_path=url,
            )
            db.session.add(material)
            added += 1
        db.session.commit()

        counts = dict(
            db.session.query(Course.name, db.func.count(Material.id))
            .join(Material)
            .filter(Material.status == STATUS_APPROVED)
            .group_by(Course.name)
            .all()
        )
        if unmatched:
            print("unmatched tops:")
            for name, count in sorted(unmatched.items(), key=lambda item: -item[1]):
                print(f"  {count:4}  {name}")
        print(f"removed samples={removed} added={added} skipped_root={skipped}")
        print(f"courses_with_files={len(counts)} total_files={sum(counts.values())}")
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]:
            print(f"  {count:4}  {name}")


if __name__ == "__main__":
    main()
