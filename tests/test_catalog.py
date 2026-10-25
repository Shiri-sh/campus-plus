from datetime import date
from types import SimpleNamespace

import pytest

from catalog import (
    approved_materials,
    explorer_options,
    parse_search_query,
    relevance_score,
    suggestion_items,
)
from extensions import db
from models import STATUS_APPROVED, STATUS_PENDING, Course, Material


def viewed_material(
    file_name="notes.pdf",
    course_name="פיזיקה",
    year=2024,
    file_type="summary",
    material_type="summaries",
):
    return SimpleNamespace(
        file_name=file_name,
        course=SimpleNamespace(name=course_name),
        academic_year=year,
        file_type=file_type,
        material_type=material_type,
    )


def add_course(name):
    course = Course(name=name)
    db.session.add(course)
    db.session.commit()
    return course


def add_material(course, file_name, **overrides):
    values = {
        "academic_year": 2024,
        "material_type": "summaries",
        "file_type": "summary",
        "uploaded_at": date(2024, 1, 1),
        "status": STATUS_APPROVED,
        "file_path": "stored.pdf",
    }
    values.update(overrides)
    material = Material(
        file_name=file_name,
        course_id=course.id,
        icon_type="pdf",
        **values,
    )
    db.session.add(material)
    db.session.commit()
    return material


def add_repeated_files(course, count):
    for index in range(count):
        add_material(course, f"קובץ-{index}.pdf")


def course_file_counts(options):
    return {course.name: course.file_count for course in options["courses"]}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (None, ("", [], None, None)),
        ("   ", ("", [], None, None)),
        (
            "  2024 מבחן אלגברה  ",
            ("2024 מבחן אלגברה", ["אלגברה"], 2024, "exam"),
        ),
        ("2020 2024", ("2020 2024", [], 2024, None)),
        ("Slides", ("Slides", [], None, "presentation")),
        ("EXAM", ("EXAM", [], None, "exam")),
    ],
)
def test_parse_search_query_pulls_out_year_and_file_type(query, expected):
    parsed = parse_search_query(query)

    assert parsed == expected


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        ([], None),
        (["notes"], 100),
        (["notes", "missing"], 50),
        (["missing"], 0),
        (["2024"], 100),
        (["פיזיקה"], 100),
    ],
)
def test_relevance_score_measures_token_hits(tokens, expected):
    score = relevance_score(viewed_material(), tokens)

    assert score == expected


def test_approved_materials_hides_pending_and_orders_newest_first(app_context):
    course = add_course("פיזיקה")
    add_material(course, "old.pdf", uploaded_at=date(2024, 1, 1))
    add_material(course, "new.pdf", uploaded_at=date(2024, 6, 1))
    add_material(course, "hidden.pdf", status=STATUS_PENDING)

    materials, year, file_type = approved_materials()

    assert [item.file_name for item in materials] == ["new.pdf", "old.pdf"]
    assert year is None
    assert file_type is None


def test_approved_materials_uses_an_explicit_year_over_the_query(app_context):
    course = add_course("פיזיקה")
    add_material(course, "old.pdf", academic_year=2020)
    add_material(course, "new.pdf", academic_year=2024)

    materials, year, _file_type = approved_materials(year=2020, query="2024")

    assert year == 2020
    assert [item.file_name for item in materials] == ["old.pdf"]


def test_approved_materials_filters_by_a_hebrew_file_type(app_context):
    course = add_course("פיזיקה")
    add_material(course, "exam.pdf", file_type="exam", material_type="exams")
    add_material(course, "notes.pdf", file_type="summary", material_type="summaries")

    materials, _year, file_type = approved_materials(query="מבחנים")

    assert file_type == "exam"
    assert [item.file_name for item in materials] == ["exam.pdf"]


def test_approved_materials_drops_files_with_no_token_hits(app_context):
    course = add_course("פיזיקה")
    add_material(course, "newton.pdf")
    add_material(course, "other.pdf")

    materials, _year, file_type = approved_materials(query="newton")

    assert file_type is None
    assert [item.file_name for item in materials] == ["newton.pdf"]
    assert materials[0].relevance == 100


@pytest.mark.parametrize("query", ["", "   ", None])
def test_suggestion_items_returns_empty_without_text(app_context, query):
    add_course("פיזיקה")

    suggestions = suggestion_items(query)

    assert suggestions == []


def test_suggestion_items_includes_a_matching_course(app_context):
    add_course("פיזיקה")
    add_course("אלגברה")

    suggestions = suggestion_items("פיז")

    assert suggestions == [{"label": "פיזיקה", "hint": "קורס"}]


def test_suggestion_items_includes_a_matching_file(app_context):
    course = add_course("פיזיקה")
    add_material(course, "newton.pdf", academic_year=2024)

    suggestions = suggestion_items("newton")

    assert suggestions == [{"label": "newton.pdf", "hint": 'פיזיקה · תשפ"ד'}]


def test_suggestion_items_includes_files_from_a_matching_course(app_context):
    course = add_course("פיזיקה")
    add_material(course, "newton.pdf", academic_year=2024)

    suggestions = suggestion_items("פיז")

    assert suggestions == [
        {"label": "פיזיקה", "hint": "קורס"},
        {"label": "newton.pdf", "hint": 'פיזיקה · תשפ"ד'},
    ]


def test_suggestion_items_returns_at_most_eight(app_context):
    course = add_course("פיזיקה")
    add_repeated_files(course, 9)

    suggestions = suggestion_items("קובץ")

    assert len(suggestions) == 8


def test_explorer_options_counts_only_approved_files(app_context):
    physics = add_course("פיזיקה")
    add_course("אלגברה")
    add_material(physics, "a.pdf")
    add_material(physics, "hidden.pdf", status=STATUS_PENDING)

    options = explorer_options()

    assert course_file_counts(options) == {"אלגברה": 0, "פיזיקה": 1}
    assert [course.name for course in options["courses_with_files"]] == ["פיזיקה"]
    assert options["years"][0] == 2026
    assert 2024 in options["years"]
    assert options["years"] == tuple(sorted(options["years"], reverse=True))
