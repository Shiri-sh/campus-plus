"""Material writes: upload confirm, approve, reject, update, delete."""

from datetime import date

from classify import MATERIAL_TO_FILE_TYPE
from commands.errors import CommandError, NotFound
from commands.support import record_after_commit
from events import (
    MATERIAL_APPROVED,
    MATERIAL_DELETED,
    MATERIAL_REJECTED,
    MATERIAL_UPDATED,
    MATERIAL_UPLOADED,
)
from extensions import db
from models import (
    ACADEMIC_YEARS,
    MATERIAL_TYPE_LABELS,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Course,
    Material,
    Report,
)

ENTITY_TYPE = "Material"
CONFIDENCE_APPROVE_AT = 70
INVALID_CLASSIFICATION = "יש לאשר או לערוך את הסיווג המוצע."
INVALID_MATERIAL_TYPE = "יש לבחור סוג חומר תקף."


def _material(material_id):
    material = db.session.get(Material, material_id)
    if material is None:
        raise NotFound()
    return material


def _recommendation(confidence):
    if (confidence or 0) >= CONFIDENCE_APPROVE_AT:
        return "approve"
    return "reject"


def confirm_upload(
    uploader_id,
    course_id,
    academic_year,
    material_type,
    file_name,
    file_path,
    icon_type,
    confidence,
):
    """Insert one pending material for a file or link the route already stored."""
    course = db.session.get(Course, course_id)
    if course is None or academic_year not in ACADEMIC_YEARS or material_type not in MATERIAL_TYPE_LABELS:
        raise CommandError(INVALID_CLASSIFICATION)

    material = Material(
        file_name=file_name,
        course_id=course.id,
        academic_year=academic_year,
        material_type=material_type,
        file_type=MATERIAL_TO_FILE_TYPE[material_type],
        icon_type=icon_type,
        uploaded_at=date.today(),
        status=STATUS_PENDING,
        file_path=file_path,
        uploader_id=uploader_id,
        confidence=confidence,
        ai_recommendation=_recommendation(confidence),
    )
    db.session.add(material)
    db.session.flush()
    record_after_commit(
        MATERIAL_UPLOADED,
        ENTITY_TYPE,
        material.id,
        actor_id=uploader_id,
        payload={
            "file_name": material.file_name,
            "course_id": material.course_id,
            "material_type": material.material_type,
            "confidence": material.confidence,
        },
    )
    return material


def approve_material(material_id, actor_id):
    material = _material(material_id)
    material.status = STATUS_APPROVED
    record_after_commit(
        MATERIAL_APPROVED,
        ENTITY_TYPE,
        material.id,
        actor_id=actor_id,
        payload={"file_name": material.file_name},
    )
    return material


def reject_material(material_id, actor_id):
    material = _material(material_id)
    material.status = STATUS_REJECTED
    record_after_commit(
        MATERIAL_REJECTED,
        ENTITY_TYPE,
        material.id,
        actor_id=actor_id,
        payload={"file_name": material.file_name},
    )
    return material


def update_material(material_id, actor_id, file_name, course_id, academic_year, material_type, lecturer):
    material = _material(material_id)
    if material_type not in MATERIAL_TYPE_LABELS:
        raise CommandError(INVALID_MATERIAL_TYPE)

    material.file_name = (file_name or material.file_name).strip()
    material.course_id = course_id
    material.academic_year = academic_year
    material.material_type = material_type
    material.file_type = MATERIAL_TO_FILE_TYPE[material_type]
    material.lecturer = (lecturer or "").strip() or None
    record_after_commit(
        MATERIAL_UPDATED,
        ENTITY_TYPE,
        material.id,
        actor_id=actor_id,
        payload={
            "file_name": material.file_name,
            "course_id": material.course_id,
            "academic_year": material.academic_year,
            "material_type": material.material_type,
        },
    )
    return material


def delete_material(material_id, actor_id):
    material = _material(material_id)
    payload = {"file_name": material.file_name}
    deleted_id = material.id
    Report.query.filter_by(material_id=deleted_id).delete()
    db.session.delete(material)
    record_after_commit(
        MATERIAL_DELETED,
        ENTITY_TYPE,
        deleted_id,
        actor_id=actor_id,
        payload=payload,
    )
