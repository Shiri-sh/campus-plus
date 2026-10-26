import logging
import os

import chromadb
from google.genai import Client

from models import hebrew_year

logger = logging.getLogger(__name__)

COLLECTION_NAME = "campus_materials"
EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_CHROMA_DIR = "instance/chroma"


def chroma_persist_dir():
    return os.environ.get("CHROMA_PERSIST_DIR") or DEFAULT_CHROMA_DIR


def material_document(material):
    """Plain-text document stored with a material vector."""
    course_name = material.course.name if getattr(material, "course", None) else ""
    parts = [
        material.file_name or "",
        course_name,
        hebrew_year(material.academic_year),
        material.material_type or "",
    ]
    summary = (getattr(material, "ai_summary", None) or "").strip()
    if summary:
        parts.append(summary[:2000])
    return " ".join(part for part in parts if part).strip()


def embed_text(text):
    """Return a Gemini embedding vector, or None when embedding is unavailable."""
    body = (text or "").strip()
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not body or not api_key:
        return None
    try:
        client = Client(api_key=api_key)
        result = client.models.embed_content(model=EMBEDDING_MODEL, contents=body)
        return list(result.embeddings[0].values)
    except Exception as error:
        logger.warning("embed_text failed: %s", error)
        return None


def _collection():
    path = chroma_persist_dir()
    os.makedirs(path, exist_ok=True)
    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(name=COLLECTION_NAME)


def upsert_material(material_id, text):
    """Store or replace the vector for one material. Returns True on success."""
    vector = embed_text(text)
    if vector is None:
        return False
    try:
        _collection().upsert(
            ids=[str(material_id)],
            embeddings=[vector],
            documents=[text],
            metadatas=[{"material_id": int(material_id)}],
        )
        return True
    except Exception as error:
        logger.warning("upsert_material failed for %s: %s", material_id, error)
        return False


def query_similar(query_text, top_k=8, filters=None):
    """Nearest neighbors in campus_materials. Empty list on any failure."""
    vector = embed_text(query_text)
    if vector is None:
        return []
    try:
        kwargs = {"query_embeddings": [vector], "n_results": max(int(top_k), 1)}
        if filters:
            kwargs["where"] = filters
        result = _collection().query(**kwargs)
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        rows = []
        for index, raw_id in enumerate(ids):
            rows.append(
                {
                    "material_id": int(raw_id),
                    "distance": distances[index] if index < len(distances) else None,
                    "document": documents[index] if index < len(documents) else None,
                }
            )
        return rows
    except Exception as error:
        logger.warning("query_similar failed: %s", error)
        return []
