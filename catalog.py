import re
import sys
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, or_

from agent.embeddings import query_similar
from extensions import db
from models import (
    ACADEMIC_YEARS,
    FILE_TYPES,
    MATERIAL_TYPES,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Course,
    Material,
    Report,
    User,
    hebrew_year,
)

ADMIN_MATERIAL_PAGE_SIZE = 80
STUDENT_MATERIAL_PAGE_SIZE = 50
ADMIN_STATUS_FILTERS = (STATUS_APPROVED, STATUS_REJECTED)

FILE_TYPE_ALIASES = {
    "exam": "exam",
    "exams": "exam",
    "מבחן": "exam",
    "מבחנים": "exam",
    "מועד": "exam",
    "summary": "summary",
    "summaries": "summary",
    "סיכום": "summary",
    "סיכומים": "summary",
    "presentation": "presentation",
    "presentations": "presentation",
    "slides": "presentation",
    "מצגת": "presentation",
    "מצגות": "presentation",
    "exercise": "exercise",
    "exercises": "exercise",
    "quiz": "exercise",
    "quizzes": "exercise",
    "תרגיל": "exercise",
    "תרגילים": "exercise",
    "תרגול": "exercise",
    "תרגולים": "exercise",
}


def parse_search_query(query):
    text = (query or "").strip()
    year = None
    file_type = None
    tokens = []

    for token in re.findall(r"[A-Za-z0-9'\u0590-\u05FF]+", text.lower()):
        year_match = re.fullmatch(r"20\d{2}", token)
        if year_match:
            year = int(token)
            continue
        if token in FILE_TYPE_ALIASES:
            file_type = FILE_TYPE_ALIASES[token]
            continue
        tokens.append(token)

    return text, tokens, year, file_type


def semantic_score(distance):
    if distance is None:
        return 50
    return int(max(0, min(100, (1 / (1 + float(distance))) * 100)))


def _semantic_hits(query):
    text = (query or "").strip()
    if not text:
        return []
    try:
        return query_similar(text, top_k=20) or []
    except Exception:
        return []


def _run_semantic_hits(query):
    current = sys.modules[__name__]
    try:
        return current._semantic_hits(query) or []
    except Exception:
        return []


def _keyword_materials(records, tokens):
    materials = records.order_by(Material.uploaded_at.desc()).all()
    if not tokens:
        for material in materials:
            material.relevance = 0
        return materials
    scored = []
    for material in materials:
        score = relevance_score(material, tokens)
        if score:
            material.relevance = score
            scored.append(material)
    return scored


def _merge_hybrid(keyword_materials, chroma_hits, filters):
    by_id = {material.id: material for material in keyword_materials}
    keyword_scores = {material.id: material.relevance or 0 for material in keyword_materials}
    chroma_ids = [row["material_id"] for row in chroma_hits if row.get("material_id") is not None]
    missing_ids = [material_id for material_id in chroma_ids if material_id not in by_id]
    if missing_ids:
        extra = Material.query.filter(
            Material.id.in_(missing_ids),
            Material.status == STATUS_APPROVED,
        )
        if filters.get("course_id"):
            extra = extra.filter_by(course_id=int(filters["course_id"]))
        if filters.get("year") is not None:
            extra = extra.filter_by(academic_year=filters["year"])
        if filters.get("material_type"):
            extra = extra.filter_by(material_type=filters["material_type"])
        if filters.get("file_type"):
            extra = extra.filter_by(file_type=filters["file_type"])
        for material in extra.all():
            by_id[material.id] = material
            keyword_scores.setdefault(material.id, 0)

    allowed = set(by_id)
    semantic_scores = {}
    for row in chroma_hits:
        material_id = row.get("material_id")
        if material_id not in allowed:
            continue
        semantic_scores[material_id] = semantic_score(row.get("distance"))

    merged = []
    for material_id, material in by_id.items():
        keyword = keyword_scores.get(material_id, 0)
        semantic = semantic_scores.get(material_id, 0)
        if keyword and semantic:
            material.relevance = int((keyword + semantic) / 2)
        else:
            material.relevance = keyword or semantic or None
        merged.append(material)
    return sorted(
        merged,
        key=lambda item: (item.relevance or 0, item.uploaded_at),
        reverse=True,
    )


def relevance_score(material, tokens):
    if not tokens:
        return None
    haystack = " ".join(
        [
            material.file_name,
            material.course.name,
            str(material.academic_year),
            material.file_type,
            material.material_type,
        ]
    ).lower()
    hits = sum(1 for token in tokens if token in haystack)
    return int((hits / len(tokens)) * 100)


def approved_materials(course_id=None, year=None, material_type=None, file_type=None, query=""):
    text, tokens, query_year, query_file_type = parse_search_query(query)
    selected_year = query_year if year is None else int(year)
    selected_file_type = file_type or query_file_type

    records = Material.query.filter_by(status=STATUS_APPROVED)
    if course_id:
        records = records.filter_by(course_id=int(course_id))
    if selected_year is not None:
        records = records.filter_by(academic_year=selected_year)
    if material_type:
        records = records.filter_by(material_type=material_type)
    if selected_file_type:
        records = records.filter_by(file_type=selected_file_type)

    executor = None
    chroma_future = None
    if text:
        executor = ThreadPoolExecutor(max_workers=1)
        chroma_future = executor.submit(_run_semantic_hits, text)
    keyword_materials = _keyword_materials(records, tokens)
    try:
        chroma_hits = chroma_future.result() if chroma_future else []
    except Exception:
        chroma_hits = []
    if executor is not None:
        executor.shutdown(wait=True)

    if not text:
        for material in keyword_materials:
            material.relevance = None
        return keyword_materials, selected_year, selected_file_type

    materials = _merge_hybrid(
        keyword_materials,
        chroma_hits,
        {
            "course_id": course_id,
            "year": selected_year,
            "material_type": material_type,
            "file_type": selected_file_type,
        },
    )
    return materials, selected_year, selected_file_type


def paginate_sequence(items, page=1, page_size=STUDENT_MATERIAL_PAGE_SIZE):
    """Return one page from an in-memory material list."""
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    total = len(items)
    if total == 0:
        return [], 0, 1, 1
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    return items[start : start + page_size], total, total_pages, page


def search_admin_materials(
    query="",
    course_id=None,
    year=None,
    material_type=None,
    status=None,
    limit=ADMIN_MATERIAL_PAGE_SIZE,
):
    """Approved and rejected materials for the admin materials tab.

    Pending rows stay on the approvals tab. An unknown status or material
    type is ignored so a bad query string does not hide the whole list.
    """
    records = Material.query.filter(Material.status != STATUS_PENDING)
    if status in ADMIN_STATUS_FILTERS:
        records = records.filter(Material.status == status)
    if course_id:
        records = records.filter(Material.course_id == course_id)
    if year is not None:
        records = records.filter(Material.academic_year == year)
    if material_type in dict(MATERIAL_TYPES):
        records = records.filter(Material.material_type == material_type)

    text = (query or "").strip()
    if text:
        pattern = f"%{text}%"
        records = records.join(Course).filter(
            or_(
                Material.file_name.ilike(pattern),
                Material.lecturer.ilike(pattern),
                Course.name.ilike(pattern),
            )
        )

    rows = (
        records.order_by(Material.uploaded_at.desc(), Material.id.desc())
        .limit(limit + 1)
        .all()
    )
    return rows[:limit], len(rows) > limit


def course_id_for_name(name):
    if not name:
        return None
    course = Course.query.filter(Course.name.ilike(name)).first()
    return None if course is None else course.id


def approved_years_for_course(course_id):
    years = [
        year
        for (year,) in db.session.query(Material.academic_year)
        .filter_by(course_id=course_id, status=STATUS_APPROVED)
        .distinct()
        .all()
        if year is not None
    ]
    return tuple(sorted(years, reverse=True))


def pending_materials():
    return (
        Material.query.filter_by(status=STATUS_PENDING)
        .order_by(Material.uploaded_at.desc())
        .all()
    )


def admin_reports():
    return Report.query.order_by(Report.created_at.desc()).all()


def student_reports(reporter_id):
    return (
        Report.query.filter_by(reporter_id=reporter_id)
        .order_by(Report.created_at.desc())
        .all()
    )


def open_report_count():
    return Report.query.filter_by(status="open").count()


def admin_users():
    return User.query.order_by(User.role, User.email).all()


def approved_course_counts(limit=8):
    return (
        db.session.query(Course.name, func.count(Material.id))
        .join(Material)
        .filter(Material.status == STATUS_APPROVED)
        .group_by(Course.name)
        .order_by(func.count(Material.id).desc())
        .limit(limit)
        .all()
    )


def courses_by_name():
    return Course.query.order_by(Course.name).all()


def suggestion_items(query):
    text, tokens, _, _ = parse_search_query(query)
    if not text:
        return []

    executor = ThreadPoolExecutor(max_workers=1)
    chroma_future = executor.submit(_run_semantic_hits, text)

    suggestions = []
    seen = set()
    courses = Course.query.order_by(Course.name).all()
    for course in courses:
        haystack = course.name.lower()
        if all(token in haystack for token in tokens) or text.lower() in haystack:
            suggestions.append({"label": course.name, "hint": "קורס"})
            seen.add(course.name)

    materials = Material.query.filter_by(status=STATUS_APPROVED).all()
    for material in materials:
        haystack = f"{material.file_name} {material.course.name}".lower()
        if all(token in haystack for token in tokens) or text.lower() in haystack:
            suggestions.append(
                {
                    "label": material.file_name,
                    "hint": f"{material.course.name} · {hebrew_year(material.academic_year)}",
                }
            )
            seen.add(material.file_name)

    try:
        chroma_hits = chroma_future.result()
    except Exception:
        chroma_hits = []
    executor.shutdown(wait=True)
    chroma_ids = [row["material_id"] for row in chroma_hits if row.get("material_id") is not None]
    if chroma_ids:
        extras = Material.query.filter(
            Material.id.in_(chroma_ids),
            Material.status == STATUS_APPROVED,
        ).all()
        extras_by_id = {item.id: item for item in extras}
        for row in chroma_hits:
            material = extras_by_id.get(row.get("material_id"))
            if material is None or material.file_name in seen:
                continue
            suggestions.append(
                {
                    "label": material.file_name,
                    "hint": f"{material.course.name} · {hebrew_year(material.academic_year)}",
                }
            )
            seen.add(material.file_name)

    return suggestions[:8]


def explorer_options():
    counts = dict(
        db.session.query(Material.course_id, func.count(Material.id))
        .filter_by(status=STATUS_APPROVED)
        .group_by(Material.course_id)
        .all()
    )
    courses = Course.query.order_by(Course.name).all()
    for course in courses:
        course.file_count = counts.get(course.id, 0)

    years = [
        year
        for (year,) in db.session.query(Material.academic_year)
        .filter_by(status=STATUS_APPROVED)
        .distinct()
        .all()
        if year is not None
    ]
    return {
        "courses": courses,
        "years": tuple(sorted(set(years) | set(ACADEMIC_YEARS), reverse=True)),
        "material_types": MATERIAL_TYPES,
        "file_types": FILE_TYPES,
        "courses_with_files": [course for course in courses if course.file_count],
    }
