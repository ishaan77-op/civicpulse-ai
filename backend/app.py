import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import Config
from database.db import db
from models.user import User
from models.complaint import Complaint
from routes.auth import auth_bp
from routes.complaints import complaint_bp
from routes.officers import officer_bp
from routes.admin import admin_bp

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)

db.init_app(app)
jwt = JWTManager(app)

with app.app_context():
    instance_path = os.path.join(os.path.dirname(__file__), "instance")
    os.makedirs(instance_path, exist_ok=True)
    db.create_all()

app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(complaint_bp, url_prefix="/api/complaints")
app.register_blueprint(officer_bp, url_prefix="/api/officers")
app.register_blueprint(admin_bp, url_prefix="/api/admin")


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    upload_folder = os.path.join(os.path.dirname(__file__), "uploads")
    return send_from_directory(upload_folder, filename)


@app.route("/")
def home():
    return {
        "message": "CivicPulse AI Backend Running 🚀"
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)