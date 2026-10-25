from datetime import date, datetime

import pytest

from commands.reports import create_report, reply_to_report
from events import REPORT_CREATED, REPORT_REPLIED
from extensions import db
from models import STATUS_APPROVED, STUDENT, Course, Event, Material, Report, User


def add_material():
    course = Course(name="פיזיקה")
    db.session.add(course)
    db.session.commit()
    material = Material(
        file_name="סיכום.pdf",
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        file_type="summary",
        icon_type="pdf",
        uploaded_at=date(2024, 1, 1),
        status=STATUS_APPROVED,
        file_path="stored.pdf",
    )
    db.session.add(material)
    db.session.commit()
    return material


def add_student(email="student@jct.ac.il"):
    user = User(email=email, password_hash="hash", role=STUDENT)
    db.session.add(user)
    db.session.commit()
    return user


def test_create_report_stores_an_open_report_and_an_event(app_context):
    material = add_material()
    student = add_student()

    report = create_report(material.id, student.id, "הקובץ לא נפתח")

    assert report.status == "open"
    assert report.message == "הקובץ לא נפתח"
    assert report.reporter_id == student.id
    event = Event.query.filter_by(event_type=REPORT_CREATED).one()
    assert event.entity_id == report.id
    assert event.actor_id == student.id


def test_reply_to_report_marks_it_answered(app_context):
    material = add_material()
    student = add_student()
    admin = add_student("admin@jct.ac.il")
    report = Report(
        material_id=material.id,
        reporter_id=student.id,
        message="שאלה",
        created_at=datetime(2024, 3, 1),
        status="open",
    )
    db.session.add(report)
    db.session.commit()

    answered = reply_to_report(report.id, admin.id, "בדקנו את הקובץ")

    assert answered.status == "answered"
    assert answered.admin_reply == "בדקנו את הקובץ"
    assert answered.replied_at is not None
    event = Event.query.filter_by(event_type=REPORT_REPLIED).one()
    assert event.actor_id == admin.id
    assert event.entity_id == report.id


def test_reply_to_report_rejects_a_missing_row(app_context):
    with pytest.raises(LookupError):
        reply_to_report(999, None, "תשובה")
