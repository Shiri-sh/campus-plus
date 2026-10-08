import re

from sqlalchemy import func

from extensions import db
from models import (
    ACADEMIC_YEARS,
    FILE_TYPES,
    MATERIAL_TYPES,
    STATUS_APPROVED,
    Course,
    Material,
)

FILE_TYPE_ALIASES = {
    "exam": "exam",
    "exams": "exam",
    "summary": "summary",
    "summaries": "summary",
    "presentation": "presentation",
    "presentations": "presentation",
    "slides": "presentation",
    "exercise": "exercise",
    "exercises": "exercise",
    "quiz": "exercise",
    "quizzes": "exercise",
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
    _, tokens, query_year, query_file_type = parse_search_query(query)
    selected_year = int(year) if year else query_year
    selected_file_type = file_type or query_file_type

    records = Material.query.filter_by(status=STATUS_APPROVED)
    if course_id:
        records = records.filter_by(course_id=int(course_id))
    if selected_year:
        records = records.filter_by(academic_year=selected_year)
    if material_type:
        records = records.filter_by(material_type=material_type)
    if selected_file_type:
        records = records.filter_by(file_type=selected_file_type)

    materials = records.order_by(Material.uploaded_at.desc()).all()

    if tokens:
        scored = []
        for material in materials:
            score = relevance_score(material, tokens)
            if score:
                material.relevance = score
                scored.append(material)
        materials = sorted(scored, key=lambda item: item.relevance, reverse=True)
    else:
        for material in materials:
            material.relevance = None

    return materials, selected_year, selected_file_type


def suggestion_items(query):
    text, tokens, _, _ = parse_search_query(query)
    if not text:
        return []

    suggestions = []
    courses = Course.query.order_by(Course.name).all()
    for course in courses:
        haystack = course.name.lower()
        if all(token in haystack for token in tokens) or text.lower() in haystack:
            suggestions.append({"label": course.name, "hint": "Course"})

    materials = Material.query.filter_by(status=STATUS_APPROVED).all()
    for material in materials:
        haystack = f"{material.file_name} {material.course.name}".lower()
        if all(token in haystack for token in tokens) or text.lower() in haystack:
            suggestions.append(
                {
                    "label": material.file_name,
                    "hint": f"{material.course.name} · {material.academic_year}",
                }
            )

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
        if year
    ]
    return {
        "courses": courses,
        "years": tuple(sorted(set(years) | set(ACADEMIC_YEARS), reverse=True)),
        "material_types": MATERIAL_TYPES,
        "file_types": FILE_TYPES,
        "courses_with_files": [course for course in courses if course.file_count],
    }
