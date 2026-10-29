"""Append-only audit log.

``record_event`` writes one ``Event`` row and commits the current session.
Call it after the business change has already been committed. On failure it
logs, rolls the session back, and returns None. It does not raise.
"""

import json
import logging

from extensions import db
from models import Event

logger = logging.getLogger(__name__)

USER_REGISTERED = "UserRegistered"
USER_BLOCKED = "UserBlocked"
USER_UNBLOCKED = "UserUnblocked"
USER_DELETED = "UserDeleted"
USER_ROLE_CHANGED = "UserRoleChanged"
MATERIAL_UPLOADED = "MaterialUploaded"
MATERIAL_APPROVED = "MaterialApproved"
MATERIAL_REJECTED = "MaterialRejected"
MATERIAL_DELETED = "MaterialDeleted"
MATERIAL_UPDATED = "MaterialUpdated"
REPORT_CREATED = "ReportCreated"
REPORT_REPLIED = "ReportReplied"
AI_EVALUATION_COMPLETED = "AIEvaluationCompleted"

EVENT_TYPES = frozenset({
    USER_REGISTERED,
    USER_BLOCKED,
    USER_UNBLOCKED,
    USER_DELETED,
    USER_ROLE_CHANGED,
    MATERIAL_UPLOADED,
    MATERIAL_APPROVED,
    MATERIAL_REJECTED,
    MATERIAL_DELETED,
    MATERIAL_UPDATED,
    REPORT_CREATED,
    REPORT_REPLIED,
    AI_EVALUATION_COMPLETED,
})


def _payload_json(payload):
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False)


def _rollback_quietly():
    try:
        db.session.rollback()
    except Exception:
        logger.exception("Failed to roll back after an audit-log error")


def record_event(event_type, entity_type, entity_id, actor_id=None, payload=None):
    """Insert one audit row and commit it. Returns the row, or None on failure."""
    if event_type not in EVENT_TYPES:
        logger.error("Rejected unknown event type: %s", event_type)
        return None
    try:
        payload_json = _payload_json(payload)
    except (TypeError, ValueError):
        logger.exception("Rejected non-JSON payload for %s", event_type)
        return None

    event = Event(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        payload=payload_json,
    )
    try:
        db.session.add(event)
        db.session.commit()
    except Exception:
        logger.exception(
            "Failed to record %s for %s %s",
            event_type,
            entity_type,
            entity_id,
        )
        _rollback_quietly()
        return None
    return event
