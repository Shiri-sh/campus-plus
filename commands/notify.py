import logging

from mcp_tools.gmail_alert import call_tool
from models import ADMIN, User

logger = logging.getLogger(__name__)


def send_mail(recipient, subject, body, *, context=""):
    recipient = (recipient or "").strip()
    if not recipient:
        logger.info("gmail_alert: no recipient %s", context)
        return {"ok": False, "confirmation": "recipient is required", "mode": "error"}
    try:
        result = call_tool(recipient, subject, body)
    except Exception as error:
        logger.warning("gmail_alert unexpected error %s: %s", context, error)
        result = {"ok": False, "confirmation": str(error), "mode": "error"}
    # #region agent log
    try:
        import json as _json, time as _time
        with open("/Users/tdinavet/Desktop/AI project/campus-plus/.cursor/debug-a47a02.log", "a") as _f:
            _f.write(_json.dumps({"sessionId":"a47a02","hypothesisId":"E","location":"commands/notify.py:send_mail","message":"send_mail","data":{"context":context,"ok":result.get("ok"),"mode":result.get("mode")},"timestamp":int(_time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    return result


def send_admin_mail(subject, body, *, context=""):
    results = []
    admins = User.query.filter_by(role=ADMIN, is_blocked=False).all()
    if not admins:
        logger.info("gmail_alert: no administrators to notify %s", context)
        return results
    for admin in admins:
        results.append(send_mail(admin.email, subject, body, context=context))
    # #region agent log
    try:
        import json as _json, time as _time
        with open("/Users/tdinavet/Desktop/AI project/campus-plus/.cursor/debug-a47a02.log", "a") as _f:
            _f.write(_json.dumps({"sessionId":"a47a02","hypothesisId":"D","location":"commands/notify.py:send_admin_mail","message":"send_admin_mail","data":{"context":context,"admin_count":len(admins),"ok_flags":[r.get("ok") for r in results],"modes":[r.get("mode") for r in results]},"timestamp":int(_time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    return results
