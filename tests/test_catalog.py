from datetime import date, datetime
from types import SimpleNamespace

import pytest

from catalog import (
    admin_reports,
    admin_users,
    approved_course_counts,
    approved_materials,
    approved_years_for_course,
    course_id_for_name,
    courses_by_name,
    explorer_options,
    open_report_count,
    parse_search_query,
    pending_materials,
    relevance_score,
    search_admin_materials,
    semantic_score,
    student_reports,
    suggestion_items,
)
from extensions import db
from models import (
    ADMIN,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STUDENT,
    Course,
    Material,
    Report,
    User,
)


def viewed_material(
    file_name="notes.pdf",
    course_name="פיזיקה",
    year=2024,
    material_type="summaries",
):
    return SimpleNamespace(
        file_name=file_name,
        course=SimpleNamespace(name=course_name),
        academic_year=year,
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


def add_user(email, role=STUDENT):
    user = User(email=email, password_hash="hash", role=role)
    db.session.add(user)
    db.session.commit()
    return user


def add_report(material, reporter, created_at, status="open"):
    report = Report(
        material_id=material.id,
        reporter_id=reporter.id,
        message="דיווח",
        created_at=created_at,
        status=status,
    )
    db.session.add(report)
    db.session.commit()
    return report


def add_repeated_files(course, count):
    for index in range(count):
        add_material(course, f"קובץ-{index}.pdf")


def add_one_file_courses(names):
    for name in names:
        add_material(add_course(name), f"{name}.pdf")


def course_file_counts(options):
    return {course.name: course.file_count for course in options["courses"]}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (None, ("", [], None, None)),
        ("   ", ("", [], None, None)),
        (
            "  2024 מבחן אלגברה  ",
            ("2024 מבחן אלגברה", ["אלגברה"], 2024, "exams"),
        ),
        ("2020 2024", ("2020 2024", [], 2024, None)),
        ("Slides", ("Slides", [], None, "presentations")),
        ("EXAM", ("EXAM", [], None, "exams")),
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


def test_approved_materials_filters_year_zero_as_a_real_year(app_context):
    course = add_course("פיזיקה")
    add_material(course, "unknown.pdf", academic_year=0)
    add_material(course, "known.pdf", academic_year=2024)

    materials, year, _file_type = approved_materials(year=0)

    assert year == 0
    assert [item.file_name for item in materials] == ["unknown.pdf"]


def test_approved_materials_uses_an_explicit_year_over_the_query(app_context):
    course = add_course("פיזיקה")
    add_material(course, "old.pdf", academic_year=2020)
    add_material(course, "new.pdf", academic_year=2024)

    materials, year, _file_type = approved_materials(year=2020, query="2024")

    assert year == 2020
    assert [item.file_name for item in materials] == ["old.pdf"]


def test_approved_materials_filters_by_a_hebrew_material_type(app_context):
    course = add_course("פיזיקה")
    add_material(course, "exam.pdf", material_type="exams")
    add_material(course, "notes.pdf", material_type="summaries")

    materials, _year, selected_type = approved_materials(query="מבחנים")

    assert selected_type == "exams"
    assert [item.file_name for item in materials] == ["exam.pdf"]


def test_approved_materials_drops_files_with_no_token_hits(app_context):
    course = add_course("פיזיקה")
    add_material(course, "newton.pdf")
    add_material(course, "other.pdf")

    materials, _year, file_type = approved_materials(query="newton")

    assert file_type is None
    assert [item.file_name for item in materials] == ["newton.pdf"]
    assert materials[0].relevance == 100


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (0, 100),
        (None, 50),
        (1, 50),
    ],
)
def test_semantic_score_converts_distance_into_zero_to_one_hundred(distance, expected):
    score = semantic_score(distance)

    assert score == expected


def test_approved_materials_merges_keyword_and_chroma_hits(app_context, monkeypatch):
    course = add_course("פיזיקה")
    add_material(course, "newton.pdf")
    semantic = add_material(course, "mechanics.pdf")
    semantic_id = semantic.id
    monkeypatch.setattr(
        "catalog._run_semantic_hits",
        lambda query: [{"material_id": semantic_id, "distance": 0.0}],
    )

    materials, _year, _file_type = approved_materials(query="newton")

    assert [item.file_name for item in materials] == ["newton.pdf", "mechanics.pdf"]
    assert materials[1].relevance == 100


def test_approved_materials_discards_chroma_hits_outside_filters(app_context, monkeypatch):
    physics = add_course("פיזיקה")
    algebra = add_course("אלגברה")
    add_material(physics, "newton.pdf")
    other = add_material(algebra, "other.pdf")
    other_id = other.id
    monkeypatch.setattr(
        "catalog._run_semantic_hits",
        lambda query: [{"material_id": other_id, "distance": 0.0}],
    )

    materials, _year, _file_type = approved_materials(course_id=physics.id, query="newton")

    assert [item.file_name for item in materials] == ["newton.pdf"]


def test_approved_materials_keeps_keyword_results_when_chroma_fails(app_context, monkeypatch):
    course = add_course("פיזיקה")
    add_material(course, "newton.pdf")

    def boom(query):
        raise RuntimeError("chroma down")

    monkeypatch.setattr("catalog._run_semantic_hits", boom)

    materials, _year, _file_type = approved_materials(query="newton")

    assert [item.file_name for item in materials] == ["newton.pdf"]


def test_suggestion_items_includes_a_chroma_hit(app_context, monkeypatch):
    course = add_course("פיזיקה")
    material = add_material(course, "mechanics.pdf", academic_year=2024)
    material_id = material.id
    monkeypatch.setattr(
        "catalog._run_semantic_hits",
        lambda query: [{"material_id": material_id, "distance": 0.1}],
    )

    suggestions = suggestion_items("גלים")

    assert suggestions == [{"label": "mechanics.pdf", "hint": 'פיזיקה · תשפ"ד'}]


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


def test_search_admin_materials_matches_a_file_name(app_context):
    course = add_course("פיזיקה")
    add_material(course, "newton.pdf")
    add_material(course, "other.pdf")

    materials, truncated = search_admin_materials(query="newton")

    assert [item.file_name for item in materials] == ["newton.pdf"]
    assert truncated is False


def test_search_admin_materials_matches_a_course_name(app_context):
    physics = add_course("פיזיקה")
    algebra = add_course("אלגברה")
    add_material(physics, "a.pdf")
    add_material(algebra, "b.pdf")

    materials, _truncated = search_admin_materials(query="אלג")

    assert [item.file_name for item in materials] == ["b.pdf"]


def test_search_admin_materials_matches_a_lecturer(app_context):
    course = add_course("פיזיקה")
    add_material(course, "a.pdf", lecturer="כהן")
    add_material(course, "b.pdf", lecturer="לוי")

    materials, _truncated = search_admin_materials(query="כהן")

    assert [item.file_name for item in materials] == ["a.pdf"]


def test_search_admin_materials_filters_rejected_and_hides_pending(app_context):
    course = add_course("פיזיקה")
    add_material(course, "ok.pdf", status=STATUS_APPROVED)
    add_material(course, "no.pdf", status=STATUS_REJECTED)
    add_material(course, "wait.pdf", status=STATUS_PENDING)

    materials, _truncated = search_admin_materials(status=STATUS_REJECTED)

    assert [item.file_name for item in materials] == ["no.pdf"]


def test_search_admin_materials_ignores_an_unknown_status(app_context):
    course = add_course("פיזיקה")
    add_material(course, "ok.pdf", status=STATUS_APPROVED)
    add_material(course, "no.pdf", status=STATUS_REJECTED)
    add_material(course, "wait.pdf", status=STATUS_PENDING)

    materials, _truncated = search_admin_materials(status="pending")

    assert [item.file_name for item in materials] == ["no.pdf", "ok.pdf"]


def test_search_admin_materials_applies_course_year_and_type_together(app_context):
    physics = add_course("פיזיקה")
    algebra = add_course("אלגברה")
    add_material(
        physics,
        "match.pdf",
        academic_year=2023,
        material_type="exams",
    )
    add_material(
        physics,
        "other-year.pdf",
        academic_year=2024,
        material_type="exams",
    )
    add_material(
        algebra,
        "other-course.pdf",
        academic_year=2023,
        material_type="exams",
    )

    materials, _truncated = search_admin_materials(
        course_id=physics.id,
        year=2023,
        material_type="exams",
    )

    assert [item.file_name for item in materials] == ["match.pdf"]


def test_search_admin_materials_ignores_an_unknown_material_type(app_context):
    course = add_course("פיזיקה")
    add_material(course, "exam.pdf", material_type="exams")
    add_material(course, "notes.pdf")

    materials, _truncated = search_admin_materials(material_type="nope")

    assert [item.file_name for item in materials] == ["notes.pdf", "exam.pdf"]


def test_search_admin_materials_reports_when_more_rows_exist(app_context):
    course = add_course("פיזיקה")
    add_material(course, "older.pdf", uploaded_at=date(2024, 1, 1))
    add_material(course, "newer.pdf", uploaded_at=date(2024, 6, 1))

    materials, truncated = search_admin_materials(limit=1)

    assert [item.file_name for item in materials] == ["newer.pdf"]
    assert truncated is True


def test_course_id_for_name_matches_an_existing_course(app_context):
    course = add_course("פיזיקה")

    matched_id = course_id_for_name("פיזיקה")

    assert matched_id == course.id


def test_course_id_for_name_returns_none_when_no_course_matches(app_context):
    add_course("פיזיקה")

    matched_id = course_id_for_name("אלגברה")

    assert matched_id is None


def test_approved_years_for_course_returns_distinct_years_newest_first(app_context):
    course = add_course("פיזיקה")
    add_material(course, "a.pdf", academic_year=2022)
    add_material(course, "b.pdf", academic_year=2024)
    add_material(course, "c.pdf", academic_year=2022)

    years = approved_years_for_course(course.id)

    assert years == (2024, 2022)


def test_approved_years_for_course_includes_year_zero(app_context):
    course = add_course("פיזיקה")
    add_material(course, "unknown.pdf", academic_year=0)
    add_material(course, "known.pdf", academic_year=2024)

    years = approved_years_for_course(course.id)

    assert years == (2024, 0)


def test_approved_years_for_course_is_empty_when_the_course_has_none(app_context):
    course = add_course("פיזיקה")
    add_material(course, "wait.pdf", status=STATUS_PENDING, academic_year=2024)

    years = approved_years_for_course(course.id)

    assert years == ()


def test_pending_materials_returns_newest_upload_first(app_context):
    course = add_course("פיזיקה")
    add_material(course, "old.pdf", status=STATUS_PENDING, uploaded_at=date(2024, 1, 1))
    add_material(course, "new.pdf", status=STATUS_PENDING, uploaded_at=date(2024, 6, 1))
    add_material(course, "ok.pdf", status=STATUS_APPROVED)

    materials = pending_materials()

    assert [item.file_name for item in materials] == ["new.pdf", "old.pdf"]


def test_admin_reports_returns_newest_first(app_context):
    course = add_course("פיזיקה")
    material = add_material(course, "notes.pdf")
    reporter = add_user("student@jct.ac.il")
    add_report(material, reporter, datetime(2024, 1, 1))
    add_report(material, reporter, datetime(2024, 6, 1))

    reports = admin_reports()

    assert [item.created_at for item in reports] == [
        datetime(2024, 6, 1),
        datetime(2024, 1, 1),
    ]


def test_student_reports_returns_only_that_students_rows(app_context):
    course = add_course("פיזיקה")
    material = add_material(course, "notes.pdf")
    owner = add_user("me@jct.ac.il")
    other = add_user("other@jct.ac.il")
    mine = add_report(material, owner, datetime(2024, 6, 1), status="answered")
    add_report(material, other, datetime(2024, 7, 1))

    reports = student_reports(owner.id)

    assert [item.id for item in reports] == [mine.id]
    assert reports[0].admin_reply is None
    assert reports[0].status == "answered"


def test_student_reports_orders_newest_first(app_context):
    course = add_course("פיזיקה")
    material = add_material(course, "notes.pdf")
    owner = add_user("me@jct.ac.il")
    add_report(material, owner, datetime(2024, 1, 1), status="open")
    add_report(material, owner, datetime(2024, 6, 1), status="answered")

    reports = student_reports(owner.id)

    assert [item.created_at for item in reports] == [
        datetime(2024, 6, 1),
        datetime(2024, 1, 1),
    ]


def test_open_report_count_ignores_answered_reports(app_context):
    course = add_course("פיזיקה")
    material = add_material(course, "notes.pdf")
    reporter = add_user("student@jct.ac.il")
    add_report(material, reporter, datetime(2024, 1, 1), status="open")
    add_report(material, reporter, datetime(2024, 2, 1), status="answered")

    count = open_report_count()

    assert count == 1


def test_admin_users_orders_by_role_then_email(app_context):
    add_user("b-student@jct.ac.il", STUDENT)
    add_user("a-student@jct.ac.il", STUDENT)
    add_user("z-admin@jct.ac.il", ADMIN)

    users = admin_users()

    assert [user.email for user in users] == [
        "z-admin@jct.ac.il",
        "a-student@jct.ac.il",
        "b-student@jct.ac.il",
    ]


def test_approved_course_counts_ranks_by_approved_file_count(app_context):
    physics = add_course("פיזיקה")
    algebra = add_course("אלגברה")
    add_material(physics, "a.pdf")
    add_material(physics, "b.pdf")
    add_material(algebra, "c.pdf")
    add_material(algebra, "hidden.pdf", status=STATUS_PENDING)

    distribution = approved_course_counts()

    assert distribution == [("פיזיקה", 2), ("אלגברה", 1)]


def test_approved_course_counts_returns_at_most_eight(app_context):
    add_one_file_courses(
        (
            "קורס-0",
            "קורס-1",
            "קורס-2",
            "קורס-3",
            "קורס-4",
            "קורס-5",
            "קורס-6",
            "קורס-7",
            "קורס-8",
        )
    )

    distribution = approved_course_counts()

    assert len(distribution) == 8


def test_courses_by_name_orders_alphabetically(app_context):
    add_course("פיזיקה")
    add_course("אלגברה")

    courses = courses_by_name()

    assert [course.name for course in courses] == ["אלגברה", "פיזיקה"]


def test_explorer_options_includes_year_zero_from_approved_files(app_context):
    course = add_course("פיזיקה")
    add_material(course, "unknown.pdf", academic_year=0)

    options = explorer_options()

    assert 0 in options["years"]
    assert options["years"] == tuple(sorted(options["years"], reverse=True))


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
