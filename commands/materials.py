import logging
from datetime import date
from pathlib import Path

from flask import current_app

from agent.embeddings import material_document, upsert_material
from events import (
    MATERIAL_APPROVED,
    MATERIAL_DELETED,
    MATERIAL_REJECTED,
    MATERIAL_UPDATED,
    MATERIAL_UPLOADED,
    record_event,
)
from extensions import db
from mcp_tools.gmail_alert import call_tool
from models import (
    ACADEMIC_YEARS,
    ADMIN,
    MATERIAL_TYPES,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Course,
    Material,
    Report,
    User,
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
    results = []
    admins = User.query.filter_by(role=ADMIN, is_blocked=False).all()
    if not admins:
        logger.info("gmail_alert: no administrators to notify for material %s", material.id)
        return results
    for admin in admins:
        try:
            results.append(call_tool(admin.email, subject, body))
        except Exception as error:
            logger.warning("gmail_alert unexpected error for %s: %s", admin.email, error)
            results.append({"ok": False, "confirmation": str(error), "mode": "error"})
    return results


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
    confidence = prediction.get("confidence")
    material = Material(
        file_name=pending["original_name"] if not pending["video_link"] else "קישור לוידאו",
        course_id=course.id,
        academic_year=academic_year,
        material_type=material_type,
        icon_type=pending["icon_type"],
        uploaded_at=date.today(),
        status=STATUS_PENDING,
        file_path=file_path,
        uploader_id=uploader_id,
        confidence=confidence,
        ai_recommendation="approve" if (confidence or 0) >= 70 else "reject",
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


def approve_material(material_id, actor_id):
    material = _require_material(material_id)
    material.status = STATUS_APPROVED
    db.session.commit()
    _record_material_event(MATERIAL_APPROVED, material, actor_id)
    try:
        upsert_material(material.id, material_document(material))
    except Exception as error:
        logger.warning("chroma upsert skipped after approve %s: %s", material.id, error)
    return material


def reject_material(material_id, actor_id):
    material = _require_material(material_id)
    material.status = STATUS_REJECTED
    db.session.commit()
    _record_material_event(MATERIAL_REJECTED, material, actor_id)
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
