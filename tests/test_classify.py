from datetime import date

import pytest

import classify
from classify import classify_source, predict_course, predict_material_type, predict_year, tokenize
from extensions import db
from models import Course
from tests.support import freeze_module_date


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, []),
        ("", []),
        ("ab", []),
        ("abc", ["abc"]),
        ("א", []),
        ("אב", ["אב"]),
        ("Exam 2024", ["exam", "2024"]),
    ],
)
def test_tokenize_keeps_hebrew_pairs_and_longer_latin(text, expected):
    tokens = tokenize(text)

    assert tokens == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("מבחן סופי", ("exams", "exam", 86)),
        ("exam slides", ("exams", "exam", 86)),
        ("quiz 3", ("quizzes", "exercise", 86)),
        ("סיכום", ("summaries", "summary", 86)),
        ("hw", ("summaries", "summary", 48)),
        ("", ("summaries", "summary", 48)),
        (None, ("summaries", "summary", 48)),
    ],
)
def test_predict_material_type_uses_the_first_matching_rule(text, expected):
    prediction = predict_material_type(text)

    assert prediction == expected


@pytest.mark.parametrize(
    ("text", "today", "expected"),
    [
        ("סיכום 2024", date(2030, 1, 1), (2024, 90)),
        ("סיכום 2030", date(2024, 1, 1), (2024, 42)),
        ("סיכום 2017", date(2024, 1, 1), (2024, 42)),
        ("סיכום", date(2024, 1, 1), (2024, 42)),
        ("סיכום", date(2030, 1, 1), (2026, 42)),
        (None, date(2024, 1, 1), (2024, 42)),
    ],
)
def test_predict_year_prefers_a_known_academic_year(monkeypatch, text, today, expected):
    freeze_module_date(monkeypatch, classify, today)

    prediction = predict_year(text)

    assert prediction == expected


def test_predict_course_requires_at_least_one_course(app_context):
    with pytest.raises(IndexError):
        predict_course("פיזיקה")


def test_predict_course_picks_the_closer_name(app_context):
    exact = Course(name="מבוא")
    broad = Course(name="מבוא לפיזיקה")
    db.session.add_all([exact, broad])
    db.session.commit()

    course, confidence = predict_course("מבוא")

    assert course.id == exact.id
    assert confidence == 96


def test_predict_course_falls_back_when_nothing_overlaps(app_context):
    db.session.add_all([Course(name="פיזיקה"), Course(name="אלגברה")])
    db.session.commit()
    algebra_id = Course.query.filter_by(name="אלגברה").one().id

    course, confidence = predict_course("hello xyz")

    assert course.id == algebra_id
    assert confidence == 40


def test_classify_source_combines_course_year_and_type(app_context, monkeypatch):
    freeze_module_date(monkeypatch, classify, date(2030, 1, 1))
    course = Course(name="פיזיקה")
    db.session.add(course)
    db.session.commit()

    result = classify_source("פיזיקה מבחן 2024")

    assert result == {
        "course_id": course.id,
        "course_name": "פיזיקה",
        "academic_year": 2024,
        "material_type": "exams",
        "material_type_label": "מבחנים",
        "file_type": "exam",
        "confidence": 90,
    }
