import logging
from datetime import date
from pathlib import Path

from flask import current_app

from agent.embeddings import material_document, upsert_material
from classify import MATERIAL_TO_FILE_TYPE
from events import (
    MATERIAL_APPROVED,
    MATERIAL_DELETED,
    MATERIAL_REJECTED,
    MATERIAL_UPDATED,
    MATERIAL_UPLOADED,
    record_event,
)
from commands.notify import send_admin_mail, send_mail
from extensions import db
from models import (
    ACADEMIC_YEARS,
    MATERIAL_TYPES,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Course,
    Material,
    Report,
)

logger = logging.getLogger(__name__)


def notify_admins_of_pending_upload(material, admin_approvals_url):
    uploader = material.uploader
    uploader_email = uploader.email if uploader else "—"
    subject = f"Campus+: חומר חדש ממתין לאישור — {material.file_name}"
    body = (
        "הועלה חומר חדש שממתין לאישור.\n\n"
        f"מעלה: {uploader_email}\n"
        f"קורס: {material.course.name}\n"
        f"שנה: {material.academic_year}\n"
        f"סוג: {material.material_type_label}\n"
        f"קובץ: {material.file_name}\n\n"
        f"לאישור:\n{admin_approvals_url}\n"
    )
    return send_admin_mail(subject, body, context=f"for material {material.id}")


def notify_uploader_of_decision(material, student_url=None):
    uploader = material.uploader
    if uploader is None or not (uploader.email or "").strip():
        logger.info("gmail_alert: no uploader to notify for material %s", material.id)
        return None
    course_name = material.course.name if material.course else "—"
    if material.status == STATUS_APPROVED:
        subject = f"Campus+: החומר אושר — {material.file_name}"
        outcome = "אושר ויופיע בקטלוג הסטודנטים."
    elif material.status == STATUS_REJECTED:
        subject = f"Campus+: החומר נדחה — {material.file_name}"
        outcome = "נדחה ולא יופיע בקטלוג."
    else:
        return None
    body = (
        f"החומר שהעלית {outcome}\n\n"
        f"קובץ: {material.file_name}\n"
        f"קורס: {course_name}\n"
        f"שנה: {material.academic_year}\n"
    )
    if student_url and material.status == STATUS_APPROVED:
        body += f"\nלקטלוג:\n{student_url}\n"
    return send_mail(
        uploader.email,
        subject,
        body,
        context=f"for uploader of material {material.id}",
    )


def confirm_pending_upload(
    pending,
    *,
    course_id,
    academic_year,
    material_type,
    uploader_id,
    admin_approvals_url,
    already_notified=False,
):
    course = db.session.get(Course, course_id)
    if (
        course is None
        or academic_year not in ACADEMIC_YEARS
        or material_type not in dict(MATERIAL_TYPES)
    ):
        raise ValueError("invalid classification")

    file_path = pending["video_link"] or pending["stored_name"]
    prediction = pending.get("prediction") or {}
    confidence = prediction.get("ai_confidence")
    if confidence is None:
        confidence = prediction.get("confidence")
    recommendation = prediction.get("ai_recommendation")
    if recommendation not in {"approve", "reject"}:
        recommendation = "approve" if (confidence or 0) >= 70 else "reject"
    material = Material(
        file_name=pending["original_name"] if not pending["video_link"] else "קישור לוידאו",
        course_id=course.id,
        academic_year=academic_year,
        material_type=material_type,
        file_type=MATERIAL_TO_FILE_TYPE[material_type],
        icon_type=pending["icon_type"],
        uploaded_at=date.today(),
        status=STATUS_PENDING,
        file_path=file_path,
        uploader_id=uploader_id,
        confidence=confidence,
        ai_recommendation=recommendation,
        ai_summary=prediction.get("ai_summary"),
    )
    db.session.add(material)
    db.session.commit()
    record_event(
        MATERIAL_UPLOADED,
        "Material",
        material.id,
        actor_id=uploader_id,
        payload={
            "file_name": material.file_name,
            "course_id": material.course_id,
            "academic_year": material.academic_year,
            "material_type": material.material_type,
        },
    )
    if not already_notified:
        try:
            notify_admins_of_pending_upload(material, admin_approvals_url)
        except Exception as error:
            logger.warning("gmail_alert skipped after save: %s", error)
    return material


def remove_stored_upload(file_path, upload_folder=None):
    """Remove a student upload from disk. Drive and other http(s) URLs are left alone."""
    if not file_path or str(file_path).startswith(("http://", "https://")):
        return
    folder = Path(upload_folder or current_app.config["UPLOAD_FOLDER"])
    stored_name = Path(file_path).name
    if stored_name in {"", ".", ".."}:
        return
    target = folder / stored_name
    try:
        folder = folder.resolve()
        target = target.resolve()
        if target.parent != folder:
            logger.warning("Refused to delete %s: outside the upload folder", file_path)
            return
        target.unlink()
    except FileNotFoundError:
        return
    except OSError as error:
        logger.warning("Could not remove stored upload %s: %s", file_path, error)


def _require_material(material_id):
    material = db.session.get(Material, material_id)
    if material is None:
        raise LookupError(f"material {material_id} not found")
    return material


def _record_material_event(event_type, material, actor_id):
    record_event(
        event_type,
        "Material",
        material.id,
        actor_id=actor_id,
        payload={"file_name": material.file_name, "status": material.status},
    )


def _notify_uploader_after_decision(material, student_url):
    try:
        notify_uploader_of_decision(material, student_url)
    except Exception as error:
        logger.warning("gmail_alert skipped after decision %s: %s", material.id, error)


def approve_material(material_id, actor_id, student_url=None):
    material = _require_material(material_id)
    material.status = STATUS_APPROVED
    db.session.commit()
    _record_material_event(MATERIAL_APPROVED, material, actor_id)
    try:
        upsert_material(material.id, material_document(material))
    except Exception as error:
        logger.warning("chroma upsert skipped after approve %s: %s", material.id, error)
    _notify_uploader_after_decision(material, student_url)
    return material


def reject_material(material_id, actor_id, student_url=None):
    material = _require_material(material_id)
    material.status = STATUS_REJECTED
    db.session.commit()
    _record_material_event(MATERIAL_REJECTED, material, actor_id)
    _notify_uploader_after_decision(material, student_url)
    return material


def update_material(
    material_id,
    actor_id,
    *,
    file_name,
    course_id,
    academic_year,
    material_type,
    lecturer,
):
    material = _require_material(material_id)
    if material_type not in dict(MATERIAL_TYPES):
        raise ValueError("invalid material type")
    cleaned_name = (file_name or "").strip()
    material.file_name = cleaned_name or material.file_name
    material.course_id = course_id
    material.academic_year = academic_year
    material.material_type = material_type
    material.file_type = MATERIAL_TO_FILE_TYPE[material_type]
    material.lecturer = (lecturer or "").strip() or None
    db.session.commit()
    _record_material_event(MATERIAL_UPDATED, material, actor_id)
    return material


def delete_material(material_id, actor_id):
    material = _require_material(material_id)
    file_path = material.file_path
    file_name = material.file_name
    Report.query.filter_by(material_id=material.id).delete()
    db.session.delete(material)
    db.session.commit()
    record_event(
        MATERIAL_DELETED,
        "Material",
        material_id,
        actor_id=actor_id,
        payload={"file_name": file_name},
    )
    remove_stored_upload(file_path)
