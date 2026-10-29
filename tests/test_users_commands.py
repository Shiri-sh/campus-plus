from datetime import date, datetime

import pytest

from commands.users import (
    create_user_by_admin,
    delete_user,
    register_user,
    set_blocked,
    set_user_role,
)
from events import (
    USER_BLOCKED,
    USER_DELETED,
    USER_REGISTERED,
    USER_ROLE_CHANGED,
    USER_UNBLOCKED,
)
from extensions import db
from models import ADMIN, STATUS_PENDING, STUDENT, Course, Event, Material, Report, User


def test_register_user_hashes_the_password_and_records_the_user(app_context):
    user = register_user("new@jct.ac.il", "secret-pass", STUDENT)

    assert user.email == "new@jct.ac.il"
    assert user.role == STUDENT
    assert user.check_password("secret-pass")
    assert user.last_login_at is not None
    event = Event.query.filter_by(event_type=USER_REGISTERED).one()
    assert event.entity_id == user.id
    assert event.actor_id == user.id


def test_set_blocked_records_block_and_unblock(app_context):
    admin = User(email="admin@jct.ac.il", password_hash="hash", role=ADMIN)
    student = User(email="student@jct.ac.il", password_hash="hash", role=STUDENT)
    db.session.add_all([admin, student])
    db.session.commit()

    blocked = set_blocked(student.id, admin.id, True)
    assert blocked.is_blocked is True
    assert Event.query.filter_by(event_type=USER_BLOCKED, actor_id=admin.id).count() == 1

    opened = set_blocked(student.id, admin.id, False)
    assert opened.is_blocked is False
    assert Event.query.filter_by(event_type=USER_UNBLOCKED, actor_id=admin.id).count() == 1


def _enable_foreign_keys():
    connection = db.session.connection()
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_delete_user_detaches_materials_removes_reports_and_records_the_event(app_context):
    _enable_foreign_keys()
    admin = User(email="admin@jct.ac.il", password_hash="hash", role=ADMIN)
    db.session.add(admin)
    db.session.commit()
    # Registration writes UserRegistered with actor_id pointing at this user.
    # Deleting them must still succeed while that audit row remains.
    student = register_user("student@jct.ac.il", "secret-pass", STUDENT)
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
        status=STATUS_PENDING,
        file_path="stored.pdf",
        uploader_id=student.id,
    )
    db.session.add(material)
    db.session.commit()
    report = Report(
        material_id=material.id,
        reporter_id=student.id,
        message="דיווח",
        created_at=datetime(2024, 2, 1),
    )
    db.session.add(report)
    db.session.commit()
    student_id = student.id

    delete_user(student_id, admin.id)

    assert db.session.get(User, student_id) is None
    assert db.session.get(Material, material.id).uploader_id is None
    assert Report.query.count() == 0
    registered = Event.query.filter_by(event_type=USER_REGISTERED).one()
    assert registered.entity_id == student_id
    assert registered.actor_id == student_id
    deleted = Event.query.filter_by(event_type=USER_DELETED).one()
    assert deleted.entity_id == student_id
    assert deleted.actor_id == admin.id


def test_user_commands_reject_a_missing_row(app_context):
    with pytest.raises(LookupError):
        set_blocked(999, None, True)
    with pytest.raises(LookupError):
        delete_user(999, None)
    with pytest.raises(LookupError):
        set_user_role(999, STUDENT, None)


def test_create_user_by_admin_records_actor_and_role(app_context):
    admin = User(email="admin@jct.ac.il", password_hash="hash", role=ADMIN)
    db.session.add(admin)
    db.session.commit()

    created = create_user_by_admin("new-admin@jct.ac.il", "secret-pass", ADMIN, admin.id)

    assert created.role == ADMIN
    assert created.check_password("secret-pass")
    event = Event.query.filter_by(event_type=USER_REGISTERED, entity_id=created.id).one()
    assert event.actor_id == admin.id


def test_set_user_role_promotes_and_demotes_with_audit(app_context):
    admin = User(email="admin@jct.ac.il", password_hash="hash", role=ADMIN)
    student = User(email="student@jct.ac.il", password_hash="hash", role=STUDENT)
    db.session.add_all([admin, student])
    db.session.commit()

    promoted = set_user_role(student.id, ADMIN, admin.id)
    assert promoted.role == ADMIN
    changed = Event.query.filter_by(event_type=USER_ROLE_CHANGED, entity_id=student.id).one()
    assert changed.actor_id == admin.id

    demoted = set_user_role(student.id, STUDENT, admin.id)
    assert demoted.role == STUDENT


def test_set_user_role_rejects_demoting_the_last_admin(app_context):
    admin = User(email="admin@jct.ac.il", password_hash="hash", role=ADMIN)
    db.session.add(admin)
    db.session.commit()

    with pytest.raises(ValueError, match="last admin"):
        set_user_role(admin.id, STUDENT, admin.id)


def test_create_user_by_admin_rejects_duplicate_email(app_context):
    admin = User(email="admin@jct.ac.il", password_hash="hash", role=ADMIN)
    db.session.add(admin)
    db.session.commit()
    create_user_by_admin("peer@jct.ac.il", "secret-pass", ADMIN, admin.id)

    with pytest.raises(ValueError, match="already registered"):
        create_user_by_admin("peer@jct.ac.il", "other-pass", ADMIN, admin.id)
