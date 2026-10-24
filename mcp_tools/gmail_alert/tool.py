import json
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)

TOOL_NAME = "gmail_alert"
INPUT_SCHEMA = json.loads((Path(__file__).with_name("tool.json")).read_text(encoding="utf-8"))[
    "inputSchema"
]
OUTPUT_SCHEMA = json.loads((Path(__file__).with_name("tool.json")).read_text(encoding="utf-8"))[
    "outputSchema"
]


def parse_credentials(raw):
    value = (raw or "").strip()
    if not value:
        return None
    if value.startswith("{"):
        data = json.loads(value)
        user = (data.get("user") or data.get("email") or "").strip()
        password = data.get("password") or data.get("app_password") or ""
        if user and password:
            return user, password
        return None
    if ":" in value:
        user, password = value.split(":", 1)
        user, password = user.strip(), password.strip()
        if user and password:
            return user, password
    return None


def call_tool(recipient, subject, body):
    """MCP tool entry: send email or log a stub. Never raises to the caller."""
    recipient = (recipient or "").strip()
    subject = subject or ""
    body = body or ""
    if not recipient:
        return {"ok": False, "confirmation": "recipient is required", "mode": "error"}

    try:
        credentials = parse_credentials(os.environ.get("GMAIL_MCP_CREDENTIALS"))
    except json.JSONDecodeError as error:
        logger.warning("gmail_alert: invalid GMAIL_MCP_CREDENTIALS JSON: %s", error)
        return {"ok": False, "confirmation": "invalid credentials JSON", "mode": "error"}

    if credentials is None:
        logger.info("gmail_alert stub to=%s subject=%s", recipient, subject)
        return {
            "ok": True,
            "confirmation": f"stub-logged:{recipient}",
            "mode": "stub",
        }

    user, password = credentials
    host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("GMAIL_SMTP_PORT", "587"))
    message = EmailMessage()
    message["From"] = user
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)
    except Exception as error:
        logger.warning("gmail_alert failed to=%s: %s", recipient, error)
        return {"ok": False, "confirmation": str(error), "mode": "error"}

    confirmation = f"sent:{recipient}"
    logger.info("gmail_alert sent to=%s", recipient)
    return {"ok": True, "confirmation": confirmation, "mode": "smtp"}
