import os
class Config:
    SECRET_KEY = "civicpulse_secret_key"

    SQLALCHEMY_DATABASE_URI = "sqlite:///civicpulse.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = "super_secret_jwt_key"