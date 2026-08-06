from flask import Flask
from flask_cors import CORS

from config import Config
from database.db import db
from models.user import User

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)

db.init_app(app)

@app.route("/")
def home():
    return {
        "message": "CivicPulse AI Backend Running 🚀"
    }

if __name__ == "__main__":
    with app.app_context():
        db.create_all()      # This creates the database and all tables

    app.run(debug=True)