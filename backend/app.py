from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import Config
from database.db import db
from models.user import User
from models.complaint import Complaint
from routes.auth import auth_bp
from routes.complaints import complaint_bp

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)

db.init_app(app)
jwt = JWTManager(app)

app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(
    complaint_bp,
    url_prefix="/api/complaints"
)


@app.route("/")
def home():
    return {
        "message": "CivicPulse AI Backend Running 🚀"
    }


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)