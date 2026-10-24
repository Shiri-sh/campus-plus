import json
import logging

import pytest
from flask import Flask
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from events import (
    MATERIAL_UPDATED,
    USER_BLOCKED,
    USER_DELETED,
    USER_REGISTERED,
    record_event,
)
from extensions import db
from models import STUDENT, Event, User


@pytest.fixture
def app_context():
    app = Flask("events-test")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    db.init_app(app)

    with app.app_context():
        db.metadata.create_all(db.engine)
        yield
        db.session.rollback()
        db.session.remove()
        db.metadata.drop_all(db.engine)


def test_record_event_persists_json_payload(app_context):
    payload = {"file_name": "סיכום", "confidence": 80}

    event = record_event(
        MATERIAL_UPDATED,
        "Material",
        4,
        actor_id=None,
        payload=payload,
    )

    assert event.id is not None
    assert event.event_type == MATERIAL_UPDATED
    assert event.entity_type == "Material"
    assert event.entity_id == 4
    assert event.actor_id is None
    assert json.loads(event.payload) == payload
    assert event.created_at is not None


def test_record_event_stores_the_actor(app_context):
    user = User(email="student@jct.ac.il", password_hash="hashed", role=STUDENT)
    db.session.add(user)
    db.session.commit()

    event = record_event(USER_REGISTERED, "User", user.id, actor_id=user.id)

    assert event.actor_id == user.id
    assert event.payload is None


def test_record_event_accepts_user_deleted(app_context):
    event = record_event(USER_DELETED, "User", 3, actor_id=1, payload={"email": "student@jct.ac.il"})

    assert event.event_type == USER_DELETED
    assert json.loads(event.payload) == {"email": "student@jct.ac.il"}


def test_record_event_commits_so_rollback_keeps_the_row(app_context):
    record_event(USER_REGISTERED, "User", 1)

    db.session.rollback()
    stored = db.session.query(Event).one()

    assert stored.event_type == USER_REGISTERED


def test_record_event_appends_a_second_row(app_context):
    record_event(USER_REGISTERED, "User", 1)
    record_event(USER_BLOCKED, "User", 1, payload={"reason": "spam"})

    first, second = db.session.query(Event).order_by(Event.id).all()

    assert first.event_type == USER_REGISTERED
    assert second.event_type == USER_BLOCKED


def test_unknown_event_type_returns_none(app_context, caplog):
    with caplog.at_level(logging.ERROR):
        event = record_event("NotAnEvent", "User", 1)

    assert event is None
    assert db.session.query(Event).count() == 0
    assert "NotAnEvent" in caplog.text


def test_non_json_payload_returns_none(app_context, caplog):
    with caplog.at_level(logging.ERROR):
        event = record_event(USER_REGISTERED, "User", 1, payload={"ids": {1, 2}})

    assert event is None
    assert db.session.query(Event).count() == 0
    assert "non-JSON payload" in caplog.text


def test_commit_failure_returns_none_and_keeps_committed_rows(app_context, monkeypatch, caplog):
    user = User(email="student@jct.ac.il", password_hash="hashed", role=STUDENT)
    db.session.add(user)
    db.session.commit()
    user_id = user.id

    def fail_commit():
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    with caplog.at_level(logging.ERROR):
        event = record_event(USER_BLOCKED, "User", user_id, actor_id=user_id)

    assert event is None
    assert db.session.get(User, user_id) is not None
    assert db.session.query(Event).count() == 0
    assert "Failed to record" in caplog.text


def test_updating_an_event_row_is_rejected(app_context):
    event = record_event(USER_REGISTERED, "User", 1)
    event.payload = '{"changed": true}'

    with pytest.raises(RuntimeError, match="append-only"):
        db.session.commit()


def test_deleting_an_event_row_is_rejected(app_context):
    event = record_event(USER_REGISTERED, "User", 1)
    db.session.delete(event)

    with pytest.raises(RuntimeError, match="append-only"):
        db.session.commit()
