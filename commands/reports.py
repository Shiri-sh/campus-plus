import logging
from datetime import datetime

from commands.notify import send_admin_mail
from events import REPORT_CREATED, REPORT_REPLIED, record_event
from extensions import db
from models import Report

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
    return send_admin_mail(subject, body, context=f"for report {report.id}")


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
        results = notify_admins_of_report(report, admin_reports_url)
        logger.warning("gmail_alert report %s results=%s", report.id, results)
        # #region agent log
        try:
            import json as _json, time as _time
            with open("/Users/tdinavet/Desktop/AI project/campus-plus/.cursor/debug-a47a02.log", "a") as _f:
                _f.write(_json.dumps({"sessionId":"a47a02","hypothesisId":"A","location":"commands/reports.py:create_report","message":"report notify results","data":{"report_id":report.id,"admin_url":bool(admin_reports_url),"results":results},"timestamp":int(_time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
    except Exception as error:
        logger.warning("gmail_alert skipped after report save: %s", error)
        # #region agent log
        try:
            import json as _json, time as _time
            with open("/Users/tdinavet/Desktop/AI project/campus-plus/.cursor/debug-a47a02.log", "a") as _f:
                _f.write(_json.dumps({"sessionId":"a47a02","hypothesisId":"B","location":"commands/reports.py:create_report","message":"report notify exception","data":{"error":str(error)[:200]},"timestamp":int(_time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
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
