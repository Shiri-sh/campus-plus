from datetime import datetime

from events import REPORT_CREATED, REPORT_REPLIED, record_event
from extensions import db
from models import Report


def create_report(material_id, reporter_id, message):
    report = Report(
        material_id=material_id,
        reporter_id=reporter_id,
        message=message,
        created_at=datetime.utcnow(),
        status="open",
    )
    db.session.add(report)
    db.session.commit()
    record_event(
        REPORT_CREATED,
        "Report",
        report.id,
        actor_id=reporter_id,
        payload={"material_id": material_id},
    )
    return report


def reply_to_report(report_id, actor_id, reply):
    report = db.session.get(Report, report_id)
    if report is None:
        raise LookupError(f"report {report_id} not found")
    report.admin_reply = reply
    report.replied_at = datetime.utcnow()
    report.status = "answered"
    db.session.commit()
    record_event(
        REPORT_REPLIED,
        "Report",
        report.id,
        actor_id=actor_id,
        payload={"material_id": report.material_id},
    )
    return report
