"""Embed 80–100 approved seed materials into local ChromaDB.

Usage
-----
    python scripts/seed_embeddings.py

Requires GEMINI_API_KEY. CHROMA_PERSIST_DIR defaults to instance/chroma.
Does not change material status, confidence, or ai_summary.
"""

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from flask import Flask

from agent.embeddings import upsert_material
from db_config import resolve_database_url
from extensions import db
from models import STATUS_APPROVED, Material, hebrew_year

SEED_MIN = 80
SEED_MAX = 100
EMBED_SLEEP_SECONDS = 1.05


def material_document(material):
    course_name = material.course.name if material.course else ""
    return " ".join(
        [
            material.file_name or "",
            course_name,
            hebrew_year(material.academic_year),
            material.material_type or "",
        ]
    ).strip()


def select_seed_materials(materials, limit=SEED_MAX):
    """Spread picks across course and type, then fill up to ``limit``."""
    grouped = defaultdict(list)
    for material in materials:
        grouped[(material.course_id, material.material_type)].append(material)

    selected = []
    seen = set()
    while len(selected) < limit:
        added = False
        for bucket in grouped.values():
            if not bucket:
                continue
            material = bucket.pop(0)
            if material.id in seen:
                continue
            selected.append(material)
            seen.add(material.id)
            added = True
            if len(selected) >= limit:
                break
        if not added:
            break
    return selected[:limit]


def create_app():
    flask_app = Flask(__name__, instance_path=str(ROOT / "instance"))
    os.makedirs(flask_app.instance_path, exist_ok=True)
    url = resolve_database_url(os.environ, flask_app.instance_path)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = url
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)
    return flask_app


def main():
    app = create_app()
    with app.app_context():
        materials = (
            Material.query.filter_by(status=STATUS_APPROVED)
            .order_by(Material.id)
            .all()
        )
        selected = select_seed_materials(materials, SEED_MAX)
        if len(selected) < SEED_MIN:
            print(
                f"WARNING: only {len(selected)} approved materials available "
                f"(wanted {SEED_MIN}–{SEED_MAX}). Embedding what is there.",
                flush=True,
            )
        stored = 0
        for material in selected:
            if upsert_material(material.id, material_document(material)):
                stored += 1
            time.sleep(EMBED_SLEEP_SECONDS)
        print(f"Upserted {stored} of {len(selected)} seed vectors.", flush=True)


if __name__ == "__main__":
    main()
