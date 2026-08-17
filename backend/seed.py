import os
from app import app
from database.db import db
from models.user import User
from services.auth_service import hash_password

def seed_database():
    with app.app_context():
        db.create_all()

        users_to_seed = [
            {
                "name": "Demo Citizen",
                "email": "citizen@example.com",
                "password": "password123",
                "role": "Citizen"
            },
            {
                "name": "Demo Officer",
                "email": "officer@example.com",
                "password": "officer123",
                "role": "Officer"
            },
            {
                "name": "Demo Admin",
                "email": "admin@example.com",
                "password": "admin123",
                "role": "Admin"
            }
        ]

        for user_data in users_to_seed:
            existing = User.query.filter_by(email=user_data["email"]).first()
            if not existing:
                user = User(
                    name=user_data["name"],
                    email=user_data["email"],
                    password_hash=hash_password(user_data["password"]),
                    role=user_data["role"]
                )
                db.session.add(user)
                print(f"Seeded user: {user_data['email']} ({user_data['role']})")
            else:
                print(f"User already exists: {user_data['email']}")

        db.session.commit()

if __name__ == "__main__":
    seed_database()
