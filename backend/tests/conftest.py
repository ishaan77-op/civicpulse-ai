import os
import shutil
import sys
import tempfile
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Tests run as an explicit development environment (config.py refuses to
# fall back to insecure default secrets in any other environment).
os.environ["APP_ENV"] = "development"

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

# Same reasoning for uploaded files: route the upload folder to a temp
# directory so tests never write into the real backend/uploads folder.
_test_upload_dir = tempfile.mkdtemp(prefix="civicpulse_test_uploads_")
os.environ["UPLOAD_FOLDER"] = _test_upload_dir

# Staff-only evidence lives in its own directory, never inside the public one.
_test_private_upload_dir = tempfile.mkdtemp(prefix="civicpulse_test_private_uploads_")
os.environ["PRIVATE_UPLOAD_FOLDER"] = _test_private_upload_dir

from app import (
    app as flask_app,
    migrate_performance_schema,
    migrate_resolution_workflow_schema,
    migrate_role_change_schema,
    migrate_ward_registry_schema,
)
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
        migrate_resolution_workflow_schema()
        migrate_ward_registry_schema()
        migrate_performance_schema()
        migrate_role_change_schema()
        yield flask_app
        db.session.remove()
        db.drop_all()


def pytest_sessionfinish(session, exitstatus):
    try:
        os.remove(_test_db_path)
    except OSError:
        pass
    # Only ever removes the temp directory created above.
    shutil.rmtree(_test_upload_dir, ignore_errors=True)
    shutil.rmtree(_test_private_upload_dir, ignore_errors=True)


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


@pytest.fixture
def chief_officer_user(app):
    user = User(
        name="Test Chief Officer",
        email="chief@example.com",
        password_hash=hash_password("chief123"),
        role="Chief Officer"
    )
    db.session.add(user)
    db.session.commit()
    return user
