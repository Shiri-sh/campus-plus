import re
from datetime import date

from models import ACADEMIC_YEARS, MATERIAL_TYPES, Course

TYPE_RULES = (
    (("exam", "midterm", "final", "moed", "מבחן", "מבחנים", "מועד"), "exams"),
    (("quiz", "exercise", "homework", "assignment", "sheet", "תרגיל", "תרגילים", "תרגול"), "quizzes"),
    (("summary", "summaries", "notes", "lecture", "סיכום", "סיכומים"), "summaries"),
    (("slide", "slides", "presentation", "ppt", "מצגת", "מצגות"), "presentations"),
    (("recording", "video", "zoom", "link", "הקלטה", "הרצאה"), "recordings"),
)

ICON_BY_EXTENSION = {
    ".pdf": "pdf",
    ".ppt": "slides",
    ".pptx": "slides",
    ".doc": "pdf",
    ".docx": "pdf",
}


def tokenize(text):
    tokens = []
    for token in re.findall(r"[a-z0-9'\u0590-\u05FF]+", (text or "").lower()):
        hebrew = any("\u0590" <= char <= "\u05FF" for char in token)
        if (hebrew and len(token) >= 2) or (not hebrew and len(token) > 2):
            tokens.append(token)
    return tokens


def predict_material_type(text):
    tokens = set(tokenize(text))
    for keywords, material_type in TYPE_RULES:
        if tokens.intersection(keywords):
            return material_type, 86
    return "summaries", 48


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
    material_type, type_confidence = predict_material_type(text)
    confidence = int((course_confidence + year_confidence + type_confidence) / 3)
    return {
        "course_id": course.id,
        "course_name": course.name,
        "academic_year": year,
        "material_type": material_type,
        "material_type_label": dict(MATERIAL_TYPES)[material_type],
        "confidence": confidence,
    }
