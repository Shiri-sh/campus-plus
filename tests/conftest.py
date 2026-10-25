import os

import pytest
from flask import Flask
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from extensions import db

# Importing app.py connects to whatever DATABASE_URL resolves to, and
# load_dotenv() will not override a value that is already set. Pin this
# before test modules import the app so a developer .env cannot be opened.
os.environ["DATABASE_URL"] = "sqlite://"


@pytest.fixture
def app_context():
    app = Flask("campus-test")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    app.config["UPLOAD_FOLDER"] = "/tmp/campus-test-uploads"
    db.init_app(app)

    with app.app_context():
        db.metadata.create_all(db.engine)
        yield
        db.session.rollback()
        db.session.remove()
        db.metadata.drop_all(db.engine)
