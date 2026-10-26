from database.db import db
from utils.time_helper import utc_now

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    email = db.Column(db.String(120), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), default="Citizen")

    spam_count = db.Column(db.Integer, nullable=False, default=0)

    is_suspended = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, default=utc_now)

    def __repr__(self):
        return f"<User {self.email}>"