import logging
from datetime import datetime

from events import REPORT_CREATED, REPORT_REPLIED, record_event
from extensions import db
from mcp_tools.gmail_alert import call_tool
from models import ADMIN, Report, User

logger = logging.getLogger(__name__)


def notify_admins_of_report(report, admin_reports_url):
    reporter = report.reporter
    reporter_email = reporter.email if reporter else "—"
    material = report.material
    file_name = material.file_name if material else "—"
    subject = f"Campus+: דיווח דחוף על תוכן — {file_name}"
    body = (
        "סטודנט/ית דיווח/ה על תוכן.\n\n"
        f"מדווח/ת: {reporter_email}\n"
        f"קובץ: {file_name}\n"
        f"הודעה: {report.message}\n\n"
        f"לדיווחים:\n{admin_reports_url or ''}\n"
    )
    results = []
    admins = User.query.filter_by(role=ADMIN, is_blocked=False).all()
    if not admins:
        logger.info("gmail_alert: no administrators to notify for report %s", report.id)
        return results
    for admin in admins:
        try:
            results.append(call_tool(admin.email, subject, body))
        except Exception as error:
            logger.warning("gmail_alert unexpected error for %s: %s", admin.email, error)
            results.append({"ok": False, "confirmation": str(error), "mode": "error"})
    return results


def create_report(material_id, reporter_id, message, admin_reports_url=None):
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
    try:
        notify_admins_of_report(report, admin_reports_url)
    except Exception as error:
        logger.warning("gmail_alert skipped after report save: %s", error)
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
