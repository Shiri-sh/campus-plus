import pytest

import app as campus_app
from extensions import db
from models import ADMIN, STUDENT, User


@pytest.fixture
def register_client():
    campus_app.app.config["TESTING"] = True
    campus_app.app.config["WTF_CSRF_ENABLED"] = False
    with campus_app.app.test_client() as client:
        yield client


def test_post_register_with_admin_role_creates_student(register_client):
    email = "self-service@jct.ac.il"
    with campus_app.app.app_context():
        User.query.filter_by(email=email).delete()
        db.session.commit()

        response = register_client.post(
            "/register",
            data={
                "email": email,
                "password": "long-enough",
                "confirm_password": "long-enough",
                "role": ADMIN,
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        user = User.query.filter_by(email=email).one()
        assert user.role == STUDENT
