from datetime import datetime

from events import (
    USER_BLOCKED,
    USER_DELETED,
    USER_REGISTERED,
    USER_UNBLOCKED,
    record_event,
)
from extensions import db
from models import Material, Report, User


def register_user(email, password, role):
    user = User(email=email, role=role)
    user.set_password(password)
    user.last_login_at = datetime.utcnow()
    db.session.add(user)
    db.session.commit()
    record_event(
        USER_REGISTERED,
        "User",
        user.id,
        actor_id=user.id,
        payload={"email": email, "role": role},
    )
    return user


def set_blocked(user_id, actor_id, blocked):
    user = db.session.get(User, user_id)
    if user is None:
        raise LookupError(f"user {user_id} not found")
    user.is_blocked = blocked
    db.session.commit()
    record_event(
        USER_BLOCKED if blocked else USER_UNBLOCKED,
        "User",
        user.id,
        actor_id=actor_id,
        payload={"email": user.email},
    )
    return user


def delete_user(user_id, actor_id):
    user = db.session.get(User, user_id)
    if user is None:
        raise LookupError(f"user {user_id} not found")
    email = user.email
    Report.query.filter_by(reporter_id=user.id).delete()
    Material.query.filter_by(uploader_id=user.id).update({"uploader_id": None})
    db.session.delete(user)
    db.session.commit()
    record_event(
        USER_DELETED,
        "User",
        user_id,
        actor_id=actor_id,
        payload={"email": email},
    )
