"""User writes: register, block, unblock, delete. Login stays in the auth route."""

from commands.errors import CommandError
from commands.support import record_after_commit, utc_now
from events import USER_BLOCKED, USER_DELETED, USER_REGISTERED, USER_UNBLOCKED
from extensions import db
from models import ADMIN, ROLES, Material, Report, User

ENTITY_TYPE = "User"
MIN_PASSWORD_LENGTH = 8
INVALID_ROLE = "יש לבחור תפקיד: סטודנט/ית או מנהל/ת."
SHORT_PASSWORD = "הסיסמה חייבת להכיל לפחות 8 תווים."
DUPLICATE_EMAIL = "כתובת דוא״ל מוסדית זו כבר רשומה במערכת."
CANNOT_BLOCK = "לא ניתן לחסום חשבון זה."
CANNOT_DELETE = "לא ניתן למחוק חשבון זה."
CANNOT_DELETE_LAST_ADMIN = "לא ניתן למחוק את המנהל/ת האחרון/ה."


def register_user(email, password, role):
    if role not in ROLES:
        raise CommandError(INVALID_ROLE)
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise CommandError(SHORT_PASSWORD)
    if User.query.filter_by(email=email).first():
        raise CommandError(DUPLICATE_EMAIL)

    user = User(email=email, role=role)
    user.set_password(password)
    user.last_login_at = utc_now()
    db.session.add(user)
    db.session.flush()
    record_after_commit(
        USER_REGISTERED,
        ENTITY_TYPE,
        user.id,
        actor_id=user.id,
        payload={"email": user.email, "role": user.role},
    )
    return user


def _user_or_refuse(user_id, actor_id, message):
    user = db.session.get(User, user_id)
    if user is None or user.id == actor_id:
        raise CommandError(message)
    return user


def block_user(user_id, actor_id):
    user = _user_or_refuse(user_id, actor_id, CANNOT_BLOCK)
    if user.is_blocked:
        return user
    user.is_blocked = True
    record_after_commit(
        USER_BLOCKED,
        ENTITY_TYPE,
        user.id,
        actor_id=actor_id,
        payload={"email": user.email},
    )
    return user


def unblock_user(user_id, actor_id):
    user = _user_or_refuse(user_id, actor_id, CANNOT_BLOCK)
    if not user.is_blocked:
        return user
    user.is_blocked = False
    record_after_commit(
        USER_UNBLOCKED,
        ENTITY_TYPE,
        user.id,
        actor_id=actor_id,
        payload={"email": user.email},
    )
    return user


def delete_user(user_id, actor_id):
    user = _user_or_refuse(user_id, actor_id, CANNOT_DELETE)
    if user.role == ADMIN and User.query.filter_by(role=ADMIN).count() <= 1:
        raise CommandError(CANNOT_DELETE_LAST_ADMIN)

    deleted_id = user.id
    payload = {"email": user.email}
    Report.query.filter_by(reporter_id=deleted_id).delete()
    Material.query.filter_by(uploader_id=deleted_id).update({"uploader_id": None})
    db.session.delete(user)
    record_after_commit(
        USER_DELETED,
        ENTITY_TYPE,
        deleted_id,
        actor_id=actor_id,
        payload=payload,
    )
