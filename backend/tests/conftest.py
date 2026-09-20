import os
import sys
import tempfile
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# IMPORTANT: this must be set before `app` is imported below. `config.py`
# reads DATABASE_URL at import time, and `app.py` runs `db.create_all()`
# (plus a schema migration) at import time too. If the real default
# database URI is ever bound first, later swapping SQLALCHEMY_DATABASE_URI
# in a fixture does NOT rebind the already-created engine, and
# `db.drop_all()` in the fixture teardown would silently wipe the real
# dev database (backend/instance/civicpulse.db) instead of a test one.
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"

from app import app as flask_app
from database.db import db
from models.user import User
from services.auth_service import hash_password


@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
        "JWT_SECRET_KEY": "test_secret_key"
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def pytest_sessionfinish(session, exitstatus):
    try:
        os.remove(_test_db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def citizen_user(app):
    user = User(
        name="Test Citizen",
        email="citizen@example.com",
        password_hash=hash_password("password123"),
        role="Citizen"
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def officer_user(app):
    user = User(
        name="Test Officer",
        email="officer@example.com",
        password_hash=hash_password("officer123"),
        role="Officer"
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(app):
    user = User(
        name="Test Admin",
        email="admin@example.com",
        password_hash=hash_password("admin123"),
        role="Admin"
    )
    db.session.add(user)
    db.session.commit()
    return user
