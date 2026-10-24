import logging
from datetime import date
from pathlib import Path

from flask import current_app

from classify import MATERIAL_TO_FILE_TYPE
from extensions import db
from mcp_tools.gmail_alert import call_tool
from models import (
    ACADEMIC_YEARS,
    ADMIN,
    MATERIAL_TYPES,
    STATUS_PENDING,
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
        file_type=MATERIAL_TO_FILE_TYPE[material_type],
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


def delete_material(material):
    file_path = material.file_path
    Report.query.filter_by(material_id=material.id).delete()
    db.session.delete(material)
    db.session.commit()
    remove_stored_upload(file_path)
    return material
