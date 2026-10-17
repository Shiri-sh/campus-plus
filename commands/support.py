"""Commit a business change, then append its audit row."""

from datetime import datetime, timezone

from events import record_event
from extensions import db


def utc_now():
    """Naive UTC timestamp, matching the app's DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record_after_commit(event_type, entity_type, entity_id, actor_id=None, payload=None):
    """Commit the open change, then append one audit row.

    Flush new rows before calling so ``entity_id`` is already assigned.
    ``record_event`` commits on its own and does not raise.
    """
    db.session.commit()
    record_event(
        event_type,
        entity_type,
        entity_id,
        actor_id=actor_id,
        payload=payload,
    )
