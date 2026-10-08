import re
from datetime import date

from models import ACADEMIC_YEARS, MATERIAL_TYPES, Course

TYPE_RULES = (
    (("exam", "midterm", "final", "moed"), "exams", "exam"),
    (("quiz", "exercise", "homework", "assignment", "sheet"), "quizzes", "exercise"),
    (("summary", "summaries", "notes", "lecture"), "summaries", "summary"),
    (("slide", "slides", "presentation", "ppt"), "presentations", "presentation"),
    (("recording", "video", "zoom", "link"), "recordings", "recording"),
)

MATERIAL_TO_FILE_TYPE = {
    "exams": "exam",
    "quizzes": "exercise",
    "summaries": "summary",
    "presentations": "presentation",
    "recordings": "recording",
}

ICON_BY_EXTENSION = {
    ".pdf": "pdf",
    ".ppt": "slides",
    ".pptx": "slides",
    ".doc": "pdf",
    ".docx": "pdf",
}


def tokenize(text):
    return [token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) > 2]


def predict_material_type(text):
    tokens = set(tokenize(text))
    for keywords, material_type, file_type in TYPE_RULES:
        if tokens.intersection(keywords):
            return material_type, file_type, 86
    return "summaries", "summary", 48


def predict_year(text):
    match = re.search(r"\b(20\d{2})\b", text or "")
    if match:
        year = int(match.group(1))
        if year in ACADEMIC_YEARS:
            return year, 90
    return date.today().year if date.today().year in ACADEMIC_YEARS else ACADEMIC_YEARS[0], 42


def predict_course(text):
    tokens = set(tokenize(text))
    ranked = []
    for course in Course.query.order_by(Course.name).all():
        course_tokens = set(tokenize(course.name))
        overlap = tokens.intersection(course_tokens)
        score = len(overlap) / max(len(course_tokens), 1)
        ranked.append((score, len(overlap), course))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_score, overlap_count, course = ranked[0]
    if overlap_count:
        return course, min(96, int(58 + best_score * 42))
    return course, 40


def classify_source(text):
    course, course_confidence = predict_course(text)
    year, year_confidence = predict_year(text)
    material_type, file_type, type_confidence = predict_material_type(text)
    confidence = int((course_confidence + year_confidence + type_confidence) / 3)
    return {
        "course_id": course.id,
        "course_name": course.name,
        "academic_year": year,
        "material_type": material_type,
        "material_type_label": dict(MATERIAL_TYPES)[material_type],
        "file_type": file_type,
        "confidence": confidence,
    }
