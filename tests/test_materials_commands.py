from datetime import date, datetime

import pytest
from flask import current_app

from commands.materials import (
    approve_material,
    confirm_pending_upload,
    delete_material,
    notify_admins_of_pending_upload,
    reject_material,
    remove_stored_upload,
    update_material,
)
from events import (
    MATERIAL_APPROVED,
    MATERIAL_DELETED,
    MATERIAL_REJECTED,
    MATERIAL_UPDATED,
    MATERIAL_UPLOADED,
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


def add_course(name="פיזיקה"):
    course = Course(name=name)
    db.session.add(course)
    db.session.commit()
    return course


def add_user(email, role, is_blocked=False):
    user = User(email=email, password_hash="hash", role=role, is_blocked=is_blocked)
    db.session.add(user)
    db.session.commit()
    return user


def add_material(course, file_name="סיכום.pdf", file_path="stored.pdf", uploader_id=None):
    material = Material(
        file_name=file_name,
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        icon_type="pdf",
        uploaded_at=date(2024, 1, 1),
        status=STATUS_PENDING,
        file_path=file_path,
        uploader_id=uploader_id,
    )
    db.session.add(material)
    db.session.commit()
    return material


def pending_upload(prediction):
    return {
        "video_link": "",
        "stored_name": "stored.pdf",
        "original_name": "סיכום.pdf",
        "icon_type": "pdf",
        "prediction": prediction,
    }


@pytest.mark.parametrize("file_path", ["", None, ".", ".."])
def test_remove_stored_upload_ignores_blank_and_parent_names(tmp_path, file_path):
    upload = tmp_path / "uploads"
    upload.mkdir()
    kept = upload / "keep.pdf"
    kept.write_text("keep")

    remove_stored_upload(file_path, upload_folder=upload)

    assert kept.read_text() == "keep"


def test_remove_stored_upload_leaves_remote_urls(tmp_path):
    upload = tmp_path / "uploads"
    upload.mkdir()
    kept = upload / "preview"
    kept.write_text("keep")

    remove_stored_upload(
        "https://drive.google.com/file/d/abc/preview",
        upload_folder=upload,
    )

    assert kept.read_text() == "keep"


def test_remove_stored_upload_deletes_a_file_inside_the_folder(tmp_path):
    upload = tmp_path / "uploads"
    upload.mkdir()
    target = upload / "abc.pdf"
    target.write_text("data")

    remove_stored_upload("nested/abc.pdf", upload_folder=upload)

    assert not target.exists()


def test_remove_stored_upload_ignores_a_missing_file(tmp_path):
    upload = tmp_path / "uploads"
    upload.mkdir()

    remove_stored_upload("missing.pdf", upload_folder=upload)

    assert list(upload.iterdir()) == []


def test_remove_stored_upload_refuses_a_symlink_outside_the_folder(tmp_path):
    upload = tmp_path / "uploads"
    upload.mkdir()
    outside = tmp_path / "secret.pdf"
    outside.write_text("secret")
    link = upload / "link.pdf"
    link.symlink_to(outside)

    remove_stored_upload("link.pdf", upload_folder=upload)

    assert outside.read_text() == "secret"
    assert link.is_symlink()


def test_notify_returns_empty_when_there_are_no_admins(app_context, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "commands.materials.call_tool",
        lambda recipient, subject, body: calls.append(recipient),
    )
    course = add_course()
    material = add_material(course)

    results = notify_admins_of_pending_upload(material, "http://approvals")

    assert results == []
    assert calls == []


def test_notify_sends_only_to_active_admins(app_context, monkeypatch):
    seen = []

    def record(recipient, subject, body):
        seen.append(recipient)
        return {"ok": True, "confirmation": "stub", "mode": "stub"}

    monkeypatch.setattr("commands.materials.call_tool", record)
    add_user("admin@jct.ac.il", ADMIN)
    add_user("blocked@jct.ac.il", ADMIN, is_blocked=True)
    add_user("student@jct.ac.il", STUDENT)
    course = add_course()
    material = add_material(course)

    results = notify_admins_of_pending_upload(material, "http://approvals")

    assert seen == ["admin@jct.ac.il"]
    assert results == [{"ok": True, "confirmation": "stub", "mode": "stub"}]


def test_notify_records_an_unexpected_send_error(app_context, monkeypatch):
    def explode(recipient, subject, body):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("commands.materials.call_tool", explode)
    add_user("admin@jct.ac.il", ADMIN)
    course = add_course()
    material = add_material(course)

    results = notify_admins_of_pending_upload(material, "http://approvals")

    assert results == [{"ok": False, "confirmation": "smtp down", "mode": "error"}]


@pytest.mark.parametrize(
    ("year", "material_type"),
    [
        (2030, "summaries"),
        (0, "summaries"),
        (2024, "bogus"),
    ],
)
def test_confirm_pending_upload_rejects_invalid_classification(app_context, year, material_type):
    course = add_course()

    with pytest.raises(ValueError, match="invalid classification"):
        confirm_pending_upload(
            pending_upload({"confidence": 80}),
            course_id=course.id,
            academic_year=year,
            material_type=material_type,
            uploader_id=None,
            admin_approvals_url="http://approvals",
        )

    assert Material.query.count() == 0


def test_confirm_pending_upload_rejects_a_missing_course(app_context):
    with pytest.raises(ValueError, match="invalid classification"):
        confirm_pending_upload(
            pending_upload({"confidence": 80}),
            course_id=999,
            academic_year=2024,
            material_type="summaries",
            uploader_id=None,
            admin_approvals_url="http://approvals",
        )

    assert Material.query.count() == 0


@pytest.mark.parametrize(
    ("prediction", "recommendation"),
    [
        ({"confidence": 70}, "approve"),
        ({"confidence": 69}, "reject"),
        ({}, "reject"),
        (None, "reject"),
    ],
)
def test_confirm_pending_upload_stores_a_pending_row(app_context, prediction, recommendation):
    course = add_course()

    material = confirm_pending_upload(
        pending_upload(prediction),
        course_id=course.id,
        academic_year=2024,
        material_type="exams",
        uploader_id=None,
        admin_approvals_url="http://approvals",
        already_notified=True,
    )

    assert material.status == STATUS_PENDING
    assert material.file_name == "סיכום.pdf"
    assert material.file_path == "stored.pdf"
    assert material.ai_recommendation == recommendation
    assert Material.query.count() == 1
    event = Event.query.filter_by(event_type=MATERIAL_UPLOADED).one()
    assert event.entity_id == material.id
    assert event.actor_id is None


def test_confirm_pending_upload_stores_a_video_link(app_context):
    course = add_course()
    pending = pending_upload({"confidence": 80})
    pending["video_link"] = "https://youtu.be/abc"
    pending["stored_name"] = "ignored.mp4"

    material = confirm_pending_upload(
        pending,
        course_id=course.id,
        academic_year=2024,
        material_type="recordings",
        uploader_id=None,
        admin_approvals_url="http://approvals",
        already_notified=True,
    )

    assert material.file_name == "קישור לוידאו"
    assert material.file_path == "https://youtu.be/abc"


def test_confirm_pending_upload_notifies_after_save(app_context, monkeypatch):
    notified = []

    def record(material, url):
        notified.append((material.file_name, url))

    monkeypatch.setattr("commands.materials.notify_admins_of_pending_upload", record)
    course = add_course()

    confirm_pending_upload(
        pending_upload({"confidence": 80}),
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        uploader_id=None,
        admin_approvals_url="http://approvals",
    )

    assert notified == [("סיכום.pdf", "http://approvals")]


def test_confirm_pending_upload_skips_notify_when_already_notified(app_context, monkeypatch):
    notified = []
    monkeypatch.setattr(
        "commands.materials.notify_admins_of_pending_upload",
        lambda material, url: notified.append(url),
    )
    course = add_course()

    confirm_pending_upload(
        pending_upload({"confidence": 80}),
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        uploader_id=None,
        admin_approvals_url="http://approvals",
        already_notified=True,
    )

    assert notified == []


def test_delete_material_removes_the_row_its_reports_and_the_file(app_context, tmp_path):
    current_app.config["UPLOAD_FOLDER"] = str(tmp_path)
    course = add_course()
    student = add_user("student@jct.ac.il", STUDENT)
    material = add_material(course, file_path="gone.pdf", uploader_id=student.id)
    report = Report(
        material_id=material.id,
        reporter_id=student.id,
        message="broken file",
        created_at=datetime(2024, 3, 1),
    )
    db.session.add(report)
    db.session.commit()
    material_id = material.id
    (tmp_path / "gone.pdf").write_text("data")

    delete_material(material_id, student.id)

    assert db.session.get(Material, material_id) is None
    assert Report.query.count() == 0
    assert not (tmp_path / "gone.pdf").exists()
    event = Event.query.filter_by(event_type=MATERIAL_DELETED).one()
    assert event.entity_id == material_id
    assert event.actor_id == student.id


def test_delete_material_leaves_a_remote_file_alone(app_context, tmp_path):
    current_app.config["UPLOAD_FOLDER"] = str(tmp_path)
    course = add_course()
    material = add_material(
        course,
        file_path="https://drive.google.com/file/d/abc/preview",
    )
    material_id = material.id
    kept = tmp_path / "preview"
    kept.write_text("keep")

    delete_material(material.id, None)

    assert db.session.get(Material, material_id) is None
    assert kept.read_text() == "keep"
    assert Event.query.filter_by(event_type=MATERIAL_DELETED).count() == 1


def test_approve_upserts_a_chroma_vector(app_context, monkeypatch):
    seen = []
    monkeypatch.setattr(
        "commands.materials.upsert_material",
        lambda material_id, text: seen.append((material_id, text)) or True,
    )
    course = add_course()
    admin = add_user("admin@jct.ac.il", ADMIN)
    material = add_material(course)

    approved = approve_material(material.id, admin.id)

    assert approved.status == STATUS_APPROVED
    assert seen[0][0] == material.id
    assert "פיזיקה" in seen[0][1]


def test_approve_still_succeeds_when_chroma_upsert_fails(app_context, monkeypatch):
    def explode(material_id, text):
        raise RuntimeError("chroma down")

    monkeypatch.setattr("commands.materials.upsert_material", explode)
    course = add_course()
    admin = add_user("admin@jct.ac.il", ADMIN)
    material = add_material(course)

    approved = approve_material(material.id, admin.id)

    assert approved.status == STATUS_APPROVED


def test_approve_and_reject_record_the_actor(app_context):
    course = add_course()
    admin = add_user("admin@jct.ac.il", ADMIN)
    material = add_material(course)

    approved = approve_material(material.id, admin.id)
    assert approved.status == STATUS_APPROVED
    approved_event = Event.query.filter_by(event_type=MATERIAL_APPROVED).one()
    assert approved_event.actor_id == admin.id
    assert approved_event.entity_id == material.id

    rejected = reject_material(material.id, admin.id)
    assert rejected.status == STATUS_REJECTED
    rejected_event = Event.query.filter_by(event_type=MATERIAL_REJECTED).one()
    assert rejected_event.actor_id == admin.id


def test_update_material_writes_fields_and_an_event(app_context):
    course = add_course()
    other = add_course("אלגברה")
    admin = add_user("admin@jct.ac.il", ADMIN)
    material = add_material(course)

    updated = update_material(
        material.id,
        admin.id,
        file_name="  מבחן.pdf  ",
        course_id=other.id,
        academic_year=2023,
        material_type="exams",
        lecturer="  ד\"ר כהן  ",
    )

    assert updated.file_name == "מבחן.pdf"
    assert updated.course_id == other.id
    assert updated.academic_year == 2023
    assert updated.material_type == "exams"
    assert updated.lecturer == "ד\"ר כהן"
    event = Event.query.filter_by(event_type=MATERIAL_UPDATED).one()
    assert event.actor_id == admin.id
    assert event.entity_id == material.id


def test_update_material_keeps_the_file_name_when_the_form_is_blank(app_context):
    course = add_course()
    admin = add_user("admin@jct.ac.il", ADMIN)
    material = add_material(course, file_name="סיכום.pdf")

    updated = update_material(
        material.id,
        admin.id,
        file_name="   ",
        course_id=course.id,
        academic_year=2024,
        material_type="summaries",
        lecturer="",
    )

    assert updated.file_name == "סיכום.pdf"
    assert updated.lecturer is None


def test_material_commands_reject_a_missing_row(app_context):
    with pytest.raises(LookupError):
        approve_material(999, None)
