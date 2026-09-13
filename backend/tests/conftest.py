import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app as flask_app
from database.db import db
from models.user import User
from services.auth_service import hash_password


@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test_secret_key"
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


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
