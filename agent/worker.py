"""Background AI evaluation of pending student uploads.

Usage
-----
    python -m agent.worker
    python -m agent.worker --once

Does not change material status. Approval stays an admin action.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from google.genai import Client
from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent.embeddings import query_similar
from catalog import semantic_score
from classify import classify_source
from db_config import resolve_database_url
from events import AI_EVALUATION_COMPLETED, record_event
from extensions import db
from mcp_tools.tavily_search import call_tool as tavily_search
from models import STATUS_PENDING, Material

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 30
SUMMARY_MODEL = os.environ.get("GEMINI_SUMMARY_MODEL") or "gemini-3.5-flash"
SUMMARY_FALLBACK_MODELS = ("gemini-flash-latest", "gemini-3.8-flash")
EMBED_QUERY_CHARS = 4000


def create_app():
    flask_app = Flask("campus-worker", instance_path=str(ROOT / "instance"))
    os.makedirs(flask_app.instance_path, exist_ok=True)
    url = resolve_database_url(os.environ, flask_app.instance_path)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = url
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["UPLOAD_FOLDER"] = str(ROOT / "instance" / "uploads")
    db.init_app(flask_app)
    return flask_app


def pending_unevaluated():
    # Upload already writes keyword confidence; empty ai_summary means the
    # worker has not evaluated the file yet.
    return (
        Material.query.filter(
            Material.status == STATUS_PENDING,
            or_(Material.ai_summary.is_(None), Material.ai_summary == ""),
        )
        .order_by(Material.id)
        .all()
    )


def extract_text(material, upload_folder):
    path = material.file_path or ""
    if material.is_link or path.startswith(("http://", "https://")):
        return ""
    stored = Path(upload_folder) / Path(path).name
    if not stored.is_file():
        return ""
    suffix = stored.suffix.lower()
    try:
        if suffix == ".pdf":
            from PyPDF2 import PdfReader

            pages = PdfReader(str(stored)).pages
            return "\n".join((page.extract_text() or "") for page in pages).strip()
        if suffix in {".doc", ".docx"}:
            from docx import Document

            return "\n".join(paragraph.text for paragraph in Document(str(stored)).paragraphs).strip()
    except Exception as error:
        logger.warning("extract_text failed for material %s: %s", material.id, error)
        return ""
    return ""


def _summary_models():
    models = []
    for name in (SUMMARY_MODEL, *SUMMARY_FALLBACK_MODELS):
        if name and name not in models:
            models.append(name)
    return models


def relevance_label(confidence, recommendation):
    if recommendation == "reject" or (confidence is not None and confidence < 40):
        return "נראה לא רלוונטי ללימודים, או דורש בדיקת מנהל."
    if confidence is not None and confidence < 70:
        return "לא בטוח שזה מתאים לקטלוג."
    return "נראה חומר לימודי רלוונטי."


def generate_summary(text, fallback):
    body = (text or "").strip() or (fallback or "").strip()
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not body:
        return "לא ניתן היה לחלץ טקסט מהקובץ."
    if not api_key:
        return body[:400]
    client = Client(api_key=api_key)
    prompt = (
        "סכם בעברית בפסקה אחת חומר לימודי זה לסטודנט. "
        "אם הטקסט קצר, נסח מה יש בקובץ לפי השם והתוכן. "
        "אם זה לא חומר לימודי, אמור זאת במפורש.\n\n"
        f"{body[:6000]}"
    )
    for model in _summary_models():
        try:
            result = client.models.generate_content(model=model, contents=prompt)
            summary = (getattr(result, "text", None) or "").strip()
            if summary:
                return summary
        except Exception as error:
            logger.warning("generate_summary failed (%s): %s", model, error)
    return body[:400]


def tavily_score(payload):
    if not payload or not payload.get("ok"):
        return 20
    if payload.get("mode") == "stub":
        return 35
    if payload.get("results"):
        return 80
    return 40


def combined_confidence(similarity, tavily_payload, keyword):
    sim = semantic_score(similarity) if similarity is not None else 0
    tav = tavily_score(tavily_payload)
    key = int(keyword or 0)
    return int((sim + tav + key) / 3)


def analyze_extracted_text(text, source_label, keyword_fallback=0):
    identity = source_label or ""
    content = (text or "").strip()
    embed_query = content[:EMBED_QUERY_CHARS] or identity
    hits = query_similar(embed_query, top_k=5)
    nearest = hits[0]["distance"] if hits else None
    tavily_payload = tavily_search(content[:400] or identity)
    try:
        keyword = classify_source(content or identity).get("confidence")
    except Exception:
        keyword = keyword_fallback
    summary = generate_summary(content, identity)
    confidence = combined_confidence(nearest, tavily_payload, keyword)
    recommendation = "approve" if confidence >= 70 else "reject"
    return {
        "ai_summary": summary,
        "ai_confidence": confidence,
        "ai_recommendation": recommendation,
        "relevance": relevance_label(confidence, recommendation),
    }


def evaluate_material(material, upload_folder):
    text = extract_text(material, upload_folder)
    identity = " ".join(
        part
        for part in (
            material.course.name if material.course else "",
            material.file_name,
        )
        if part
    )
    analysis = analyze_extracted_text(
        text,
        identity or material.file_name,
        keyword_fallback=material.confidence,
    )
    material.ai_summary = analysis["ai_summary"]
    material.confidence = analysis["ai_confidence"]
    material.ai_recommendation = analysis["ai_recommendation"]
    db.session.commit()
    record_event(
        AI_EVALUATION_COMPLETED,
        "Material",
        material.id,
            payload={
                "confidence": material.confidence,
                "ai_recommendation": material.ai_recommendation,
            },
    )
    return material


def run_once(upload_folder):
    evaluated = 0
    for material in pending_unevaluated():
        try:
            evaluate_material(material, upload_folder)
            evaluated += 1
        except Exception as error:
            logger.warning("skip material %s: %s", material.id, error)
            db.session.rollback()
    return evaluated


def main(argv=None):
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Evaluate pending Campus+ uploads.")
    parser.add_argument("--once", action="store_true", help="Run a single poll cycle and exit.")
    args = parser.parse_args(argv)
    interval = int(os.environ.get("WORKER_POLL_SECONDS") or DEFAULT_POLL_SECONDS)
    app = create_app()
    upload_folder = app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    with app.app_context():
        if args.once:
            count = run_once(upload_folder)
            logger.info("worker evaluated %s pending upload(s)", count)
            return count
        while True:
            count = run_once(upload_folder)
            logger.info("worker evaluated %s pending upload(s)", count)
            time.sleep(interval)


if __name__ == "__main__":
    main()
