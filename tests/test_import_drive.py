from datetime import date

import pytest

import scripts.import_drive as import_drive
from courses import COURSE_MAP
from extensions import db
from models import STATUS_APPROVED, Course, Material
from scripts.import_drive import (
    drive_url,
    import_materials,
    infer_icon,
    infer_type,
    infer_year,
    is_study_file,
    normalize,
    remove_old_drive_rows,
)
from tests.support import freeze_module_date

TOP = "בסיסי נתונים"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  אלגברה  ", "אלגברה"),
        ("a׳b", "a'b"),
        ("a\u2019b", "a'b"),
        ("a`b", "a'b"),
        ("a&amp;b", "a&b"),
    ],
)
def test_normalize_unescapes_and_folds_apostrophes(name, expected):
    cleaned = normalize(name)

    assert cleaned == expected


@pytest.mark.parametrize(
    ("name", "path", "expected"),
    [
        ("Notes.PDF", ["course"], True),
        ("clip.mp4", ["course"], True),
        ("Main.java", ["course", "מבחן"], False),
        ("readme", ["course", "מבחן"], True),
        ("readme", ["course", "misc"], False),
    ],
)
def test_is_study_file_skips_source_files(name, path, expected):
    item = {"name": name, "path": path}

    assert is_study_file(item) is expected


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (["מבחן", "week.pdf"], ("exams", "exam")),
        (["תרגול", "week.pdf"], ("quizzes", "exercise")),
        (["מצגת", "week.pdf"], ("presentations", "presentation")),
        (["week1.mov"], ("recordings", "recording")),
        (["week1.pdf"], ("summaries", "summary")),
    ],
)
def test_infer_type_prefers_keywords_then_extension(parts, expected):
    inferred = infer_type(parts)

    assert inferred == expected


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (["year 2024.pdf"], 2024),
        (["notes2024.pdf"], 0),
        (["2019", "notes", "2024"], 2024),
        (['תשפ"ד', "2021"], 2021),
        (["2030"], 2030),
        (['תשפ"ד'], 2024),
        (["תשפ״ה"], 2025),
        (["תשפ׳ו"], 2026),
        (['תשע"ז'], 2017),
        (["folder", "תשפ", "notes.pdf"], 2020),
        (['תש"פ'], 0),
        (["מבחן.pdf"], 0),
        ([], 0),
    ],
)
def test_infer_year_prefers_gregorian_then_hebrew(parts, expected):
    year = infer_year(parts)

    assert year == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Deck.PPTX", "slides"),
        ("clip.AVI", "video"),
        ("clip.mov", "video"),
        ("notes.pdf", "pdf"),
        ("notes", "pdf"),
    ],
)
def test_infer_icon_follows_the_extension(name, expected):
    icon = infer_icon(name)

    assert icon == expected


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"id": "abc", "url": "https://drive.google.com/drive/folders/abc"}, ""),
        (
            {
                "id": "abc",
                "url": "https://docs.google.com/document/d/abc/edit?usp=share&foo=1",
            },
            "https://docs.google.com/document/d/abc/edit?usp=share",
        ),
        ({"id": "abc"}, "https://drive.google.com/file/d/abc/preview"),
    ],
)
def test_drive_url_builds_a_preview_link(item, expected):
    url = drive_url(item)

    assert url == expected


def drive_file(name, path, file_id="file-1", url=None):
    return {
        "id": file_id,
        "name": name,
        "path": path,
        "url": url if url is not None else f"https://drive.google.com/file/d/{file_id}/view",
    }


def mapped_course():
    course = Course(name=COURSE_MAP[TOP])
    db.session.add(course)
    db.session.commit()
    return course


def test_import_materials_inserts_a_mapped_study_file(app_context):
    mapped_course()
    item = drive_file("מבחן.pdf", [TOP, "2024", "מבחן.pdf"])

    added, skipped, unmatched = import_materials([item], None)

    row = Material.query.one()
    assert (added, skipped, unmatched) == (1, 0, {})
    assert row.file_name == "מבחן.pdf"
    assert row.course.name == COURSE_MAP[TOP]
    assert row.academic_year == 2024
    assert row.material_type == "exams"
    assert row.file_type == "exam"
    assert row.icon_type == "pdf"
    assert row.status == STATUS_APPROVED
    assert row.file_path == "https://drive.google.com/file/d/file-1/preview"
    assert row.uploaded_at == date(2024, 1, 1)


def test_import_materials_uses_today_when_the_year_is_unknown(app_context, monkeypatch):
    mapped_course()
    freeze_module_date(monkeypatch, import_drive, date(2024, 5, 1))
    item = drive_file("מבחן.pdf", [TOP, "מבחן.pdf"])

    import_materials([item], None)

    row = Material.query.one()
    assert row.academic_year == 0
    assert row.uploaded_at == date(2024, 5, 1)


def test_import_materials_skips_source_files(app_context):
    mapped_course()
    item = drive_file("Main.java", [TOP, "Main.java"])

    added, skipped, unmatched = import_materials([item], None)

    assert (added, skipped, unmatched) == (0, 1, {})
    assert Material.query.count() == 0


def test_import_materials_counts_an_unknown_course(app_context):
    item = drive_file("notes.pdf", ["לא קורס", "notes.pdf"])

    added, skipped, unmatched = import_materials([item], None)

    assert added == 0
    assert skipped == 1
    assert unmatched == {"לא קורס": 1}
    assert Material.query.count() == 0


def test_import_materials_skips_a_copied_top_folder(app_context):
    top = "עותק של מערכות הפעלה"
    item = drive_file("notes.pdf", [top, "notes.pdf"])

    added, skipped, unmatched = import_materials([item], None)

    assert (added, skipped, unmatched) == (0, 1, {})


def test_import_materials_stops_at_the_limit(app_context):
    mapped_course()
    first = drive_file("one.pdf", [TOP, "2024", "one.pdf"], file_id="one")
    second = drive_file("two.pdf", [TOP, "2024", "two.pdf"], file_id="two")

    added, skipped, unmatched = import_materials([first, second], 1)

    assert (added, skipped, unmatched) == (1, 0, {})
    assert Material.query.count() == 1
    assert Material.query.one().file_name == "one.pdf"


def test_import_materials_does_not_insert_a_duplicate_drive_url(app_context):
    mapped_course()
    first = drive_file("one.pdf", [TOP, "2024", "one.pdf"], file_id="same")
    second = drive_file("two.pdf", [TOP, "2024", "two.pdf"], file_id="same")

    added, skipped, unmatched = import_materials([first, second], None)

    assert (added, skipped, unmatched) == (1, 0, {})
    assert Material.query.count() == 1


def test_remove_old_drive_rows_keeps_local_files(app_context):
    course = mapped_course()
    drive_row = Material(
        file_name="drive.pdf",
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        file_type="summary",
        icon_type="pdf",
        uploaded_at=date(2024, 1, 1),
        status=STATUS_APPROVED,
        file_path="https://drive.google.com/file/d/abc/preview",
    )
    orphan = Material(
        file_name="orphan.pdf",
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        file_type="summary",
        icon_type="pdf",
        uploaded_at=date(2024, 1, 1),
        status=STATUS_APPROVED,
        file_path=None,
        uploader_id=None,
    )
    upload = Material(
        file_name="student.pdf",
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        file_type="summary",
        icon_type="pdf",
        uploaded_at=date(2024, 1, 1),
        status=STATUS_APPROVED,
        file_path="student.pdf",
        uploader_id=None,
    )
    db.session.add_all([drive_row, orphan, upload])
    db.session.commit()
    upload_id = upload.id

    removed = remove_old_drive_rows()

    assert removed == 1
    assert Material.query.one().id == upload_id
