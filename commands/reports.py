"""Report writes: a student creates one, an admin replies."""

from commands.errors import CommandError, NotFound
from commands.support import record_after_commit, utc_now
from events import REPORT_CREATED, REPORT_REPLIED
from extensions import db
from models import STATUS_APPROVED, Material, Report

ENTITY_TYPE = "Report"
REPORT_OPEN = "open"
REPORT_ANSWERED = "answered"
MISSING_MESSAGE = "יש לכתוב הודעה למנהל/ת."
MISSING_REPLY = "יש לכתוב תגובה לפני שליחה."


def create_report(material_id, reporter_id, message):
    text = (message or "").strip()
    if not text:
        raise CommandError(MISSING_MESSAGE)

    material = db.session.get(Material, material_id)
    if material is None or material.status != STATUS_APPROVED:
        raise NotFound()

    report = Report(
        material_id=material.id,
        reporter_id=reporter_id,
        message=text,
        created_at=utc_now(),
        status=REPORT_OPEN,
    )
    db.session.add(report)
    db.session.flush()
    record_after_commit(
        REPORT_CREATED,
        ENTITY_TYPE,
        report.id,
        actor_id=reporter_id,
        payload={"material_id": material.id},
    )
    return report


def reply_to_report(report_id, actor_id, reply):
    text = (reply or "").strip()
    if not text:
        raise CommandError(MISSING_REPLY)

    report = db.session.get(Report, report_id)
    if report is None:
        raise NotFound()

    report.admin_reply = text
    report.replied_at = utc_now()
    report.status = REPORT_ANSWERED
    record_after_commit(
        REPORT_REPLIED,
        ENTITY_TYPE,
        report.id,
        actor_id=actor_id,
        payload={"status": REPORT_ANSWERED},
    )
    return report
