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
        ("מבחן סופי", ("exams", 86)),
        ("exam slides", ("exams", 86)),
        ("quiz 3", ("quizzes", 86)),
        ("סיכום", ("summaries", 86)),
        ("hw", ("summaries", 48)),
        ("", ("summaries", 48)),
        (None, ("summaries", 48)),
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
    course, confidence = predict_course("פיזיקה")

    assert course is None
    assert confidence == 0


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

    course, confidence = predict_course("hello xyz")

    assert course is None
    assert confidence == 0


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
        "confidence": 90,
        "looks_academic": True,
        "relevance": "נראה חומר לימודי שמתאים לקטלוג.",
    }
