from datetime import date

from courses import COURSE_MAP
from extensions import db
from models import Course, Material
from seed import _migrate_english_courses, seed_catalog


def add_material(course, file_name):
    material = Material(
        file_name=file_name,
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        file_type="summary",
        icon_type="pdf",
        uploaded_at=date(2024, 1, 1),
    )
    db.session.add(material)
    db.session.commit()
    return material


def test_migrate_english_courses_renames_when_hebrew_is_missing(app_context):
    original = Course(name="Physics")
    db.session.add(original)
    db.session.commit()
    original_id = original.id

    _migrate_english_courses()

    renamed = db.session.get(Course, original_id)
    assert renamed.name == "פיזיקה"
    assert Course.query.filter_by(name="Physics").one_or_none() is None


def test_migrate_english_courses_moves_materials_onto_existing_hebrew(app_context):
    english = Course(name="Databases")
    hebrew = Course(name="בסיסי נתונים")
    db.session.add_all([english, hebrew])
    db.session.commit()
    material = add_material(english, "summary.pdf")
    material_id = material.id
    hebrew_id = hebrew.id

    _migrate_english_courses()

    assert Course.query.filter_by(name="Databases").one_or_none() is None
    assert Course.query.filter_by(name="בסיסי נתונים").one().id == hebrew_id
    assert db.session.get(Material, material_id).course_id == hebrew_id


def test_migrate_english_courses_leaves_an_empty_catalog_unchanged(app_context):
    _migrate_english_courses()

    assert Course.query.count() == 0


def test_seed_catalog_is_idempotent(app_context):
    seed_catalog()
    first = {course.name for course in Course.query.all()}

    seed_catalog()
    second = {course.name for course in Course.query.all()}

    assert first == second
    assert first == set(COURSE_MAP.values())
    assert Course.query.count() == len(first)
