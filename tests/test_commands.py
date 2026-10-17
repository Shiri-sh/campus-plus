import json
from datetime import date, datetime, timezone

import pytest
from flask import Flask
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from commands.errors import CommandError, NotFound
from commands.materials import (
    approve_material,
    confirm_upload,
    delete_material,
    reject_material,
    update_material,
)
from commands.reports import create_report, reply_to_report
from commands.users import block_user, delete_user, register_user, unblock_user
from events import (
    MATERIAL_APPROVED,
    MATERIAL_DELETED,
    MATERIAL_REJECTED,
    MATERIAL_UPDATED,
    MATERIAL_UPLOADED,
    REPORT_CREATED,
    REPORT_REPLIED,
    USER_BLOCKED,
    USER_DELETED,
    USER_REGISTERED,
    USER_UNBLOCKED,
)
from extensions import db
from models import (
    ADMIN,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STUDENT,
    Course,
    Event,
    Material,
    Report,
    User,
)


@pytest.fixture
def app_context():
    app = Flask("commands-test")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    db.init_app(app)

    with app.app_context():
        db.metadata.create_all(db.engine)
        yield
        db.session.rollback()
        db.session.remove()
        db.metadata.drop_all(db.engine)


def add_user(email, role=STUDENT, password="password1"):
    user = User(email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def add_course(name="מבני נתונים"):
    course = Course(name=name)
    db.session.add(course)
    db.session.commit()
    return course


def add_material(course, uploader, status=STATUS_PENDING, file_name="סיכום.pdf"):
    material = Material(
        file_name=file_name,
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        file_type="summary",
        icon_type="pdf",
        uploaded_at=date.today(),
        status=status,
        file_path="stored.pdf",
        uploader_id=uploader.id,
    )
    db.session.add(material)
    db.session.commit()
    return material


def one_event(event_type):
    return Event.query.filter_by(event_type=event_type).one()


def test_confirm_upload_stores_a_pending_material_and_records_the_event(app_context):
    student = add_user("student@jct.ac.il")
    course = add_course()

    material = confirm_upload(
        uploader_id=student.id,
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        file_name="סיכום.pdf",
        file_path="stored.pdf",
        icon_type="pdf",
        confidence=80,
    )

    assert material.status == STATUS_PENDING
    assert material.file_type == "summary"
    assert material.ai_recommendation == "approve"
    event = one_event(MATERIAL_UPLOADED)
    assert event.entity_id == material.id
    assert event.actor_id == student.id
    assert json.loads(event.payload)["file_name"] == "סיכום.pdf"


def test_confirm_upload_recommends_reject_when_confidence_is_low_or_missing(app_context):
    student = add_user("student@jct.ac.il")
    course = add_course()

    low = confirm_upload(
        uploader_id=student.id,
        course_id=course.id,
        academic_year=2024,
        material_type="exams",
        file_name="מבחן.pdf",
        file_path="exam.pdf",
        icon_type="pdf",
        confidence=69,
    )
    missing = confirm_upload(
        uploader_id=student.id,
        course_id=course.id,
        academic_year=2024,
        material_type="quizzes",
        file_name="תרגיל.pdf",
        file_path="quiz.pdf",
        icon_type="pdf",
        confidence=None,
    )

    assert low.ai_recommendation == "reject"
    assert low.file_type == "exam"
    assert missing.ai_recommendation == "reject"


def test_confirm_upload_rejects_an_unknown_course_without_an_event(app_context):
    student = add_user("student@jct.ac.il")

    with pytest.raises(CommandError):
        confirm_upload(
            uploader_id=student.id,
            course_id=999,
            academic_year=2024,
            material_type="summaries",
            file_name="סיכום.pdf",
            file_path="stored.pdf",
            icon_type="pdf",
            confidence=80,
        )

    assert Material.query.count() == 0
    assert Event.query.count() == 0


def test_approve_material_marks_it_approved_and_records_the_actor(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student)

    approved = approve_material(material.id, admin.id)

    assert approved.status == STATUS_APPROVED
    event = one_event(MATERIAL_APPROVED)
    assert event.actor_id == admin.id
    assert event.entity_id == material.id


def test_reject_material_marks_it_rejected(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student)

    rejected = reject_material(material.id, admin.id)

    assert rejected.status == STATUS_REJECTED
    assert one_event(MATERIAL_REJECTED).actor_id == admin.id


def test_update_material_changes_the_file_type_and_records_the_event(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student, status=STATUS_APPROVED)

    updated = update_material(
        material.id,
        admin.id,
        file_name="מבחן.pdf",
        course_id=material.course_id,
        academic_year=2023,
        material_type="exams",
        lecturer="ד״ר כהן",
    )

    assert updated.file_name == "מבחן.pdf"
    assert updated.file_type == "exam"
    assert updated.lecturer == "ד״ר כהן"
    assert updated.academic_year == 2023
    assert one_event(MATERIAL_UPDATED).actor_id == admin.id


def test_update_material_rejects_an_unknown_type_without_an_event(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student)

    with pytest.raises(CommandError):
        update_material(
            material.id,
            admin.id,
            file_name="סיכום.pdf",
            course_id=material.course_id,
            academic_year=2024,
            material_type="song",
            lecturer="",
        )

    assert material.material_type == "summaries"
    assert Event.query.count() == 0


def test_delete_material_removes_the_row_and_its_reports(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student, status=STATUS_APPROVED)
    material_id = material.id
    db.session.add(
        Report(
            material_id=material_id,
            reporter_id=student.id,
            message="קישור שבור",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            status="open",
        )
    )
    db.session.commit()

    delete_material(material_id, admin.id)

    assert db.session.get(Material, material_id) is None
    assert Report.query.count() == 0
    event = one_event(MATERIAL_DELETED)
    assert event.entity_id == material_id
    assert json.loads(event.payload)["file_name"] == "סיכום.pdf"


def test_approve_material_raises_not_found_for_a_missing_row(app_context):
    with pytest.raises(NotFound):
        approve_material(404, actor_id=1)

    assert Event.query.count() == 0


def test_create_report_stores_the_message_for_an_approved_material(app_context):
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student, status=STATUS_APPROVED)

    report = create_report(material.id, student.id, "  הקובץ לא נפתח  ")

    assert report.message == "הקובץ לא נפתח"
    assert report.status == "open"
    event = one_event(REPORT_CREATED)
    assert event.actor_id == student.id
    assert json.loads(event.payload)["material_id"] == material.id


def test_create_report_rejects_a_blank_message(app_context):
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student, status=STATUS_APPROVED)

    with pytest.raises(CommandError):
        create_report(material.id, student.id, "   ")

    assert Report.query.count() == 0
    assert Event.query.count() == 0


def test_create_report_hides_a_pending_material(app_context):
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student, status=STATUS_PENDING)

    with pytest.raises(NotFound):
        create_report(material.id, student.id, "בעיה")

    assert Report.query.count() == 0


def test_reply_to_report_marks_it_answered(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student, status=STATUS_APPROVED)
    report = create_report(material.id, student.id, "בעיה")

    answered = reply_to_report(report.id, admin.id, "  תוקן  ")

    assert answered.status == "answered"
    assert answered.admin_reply == "תוקן"
    assert answered.replied_at is not None
    assert one_event(REPORT_REPLIED).actor_id == admin.id


def test_register_user_hashes_the_password_and_records_the_event(app_context):
    user = register_user("student@jct.ac.il", "password1", STUDENT)

    assert user.check_password("password1")
    assert user.last_login_at is not None
    event = one_event(USER_REGISTERED)
    assert event.entity_id == user.id
    assert event.actor_id == user.id
    assert json.loads(event.payload)["email"] == "student@jct.ac.il"


def test_register_user_rejects_a_duplicate_email(app_context):
    register_user("student@jct.ac.il", "password1", STUDENT)

    with pytest.raises(CommandError):
        register_user("student@jct.ac.il", "password1", STUDENT)

    assert User.query.count() == 1
    assert Event.query.count() == 1


def test_register_user_rejects_a_short_password(app_context):
    with pytest.raises(CommandError):
        register_user("student@jct.ac.il", "short", STUDENT)

    assert User.query.count() == 0
    assert Event.query.count() == 0


def test_block_user_and_unblock_user_record_separate_events(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")

    block_user(student.id, admin.id)
    assert db.session.get(User, student.id).is_blocked is True

    unblock_user(student.id, admin.id)

    assert db.session.get(User, student.id).is_blocked is False
    assert one_event(USER_BLOCKED).actor_id == admin.id
    assert one_event(USER_UNBLOCKED).actor_id == admin.id


def test_block_user_refuses_the_actor_themselves(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)

    with pytest.raises(CommandError):
        block_user(admin.id, admin.id)

    assert admin.is_blocked is False
    assert Event.query.count() == 0


def test_block_user_does_not_append_a_second_event_when_already_blocked(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")
    block_user(student.id, admin.id)

    again = block_user(student.id, admin.id)

    assert again.is_blocked is True
    assert Event.query.filter_by(event_type=USER_BLOCKED).count() == 1


def test_delete_user_removes_reports_and_keeps_their_uploads(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    student = add_user("student@jct.ac.il")
    material = add_material(add_course(), student, status=STATUS_APPROVED)
    material_id = material.id
    student_id = student.id
    create_report(material.id, student.id, "בעיה")

    delete_user(student_id, admin.id)

    assert db.session.get(User, student_id) is None
    assert Report.query.count() == 0
    kept = db.session.get(Material, material_id)
    assert kept.uploader_id is None
    event = one_event(USER_DELETED)
    assert event.entity_id == student_id
    assert event.actor_id == admin.id
    assert json.loads(event.payload)["email"] == "student@jct.ac.il"


def test_delete_user_refuses_the_last_admin(app_context):
    admin = add_user("admin@jct.ac.il", ADMIN)
    other = add_user("student@jct.ac.il")

    with pytest.raises(CommandError):
        delete_user(admin.id, other.id)

    assert db.session.get(User, admin.id) is not None
    assert Event.query.filter_by(event_type=USER_DELETED).count() == 0
