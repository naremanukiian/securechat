import os
from flask import Flask
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

db       = SQLAlchemy()
bcrypt   = Bcrypt()
socketio = SocketIO()
login_manager = LoginManager()
limiter  = Limiter(key_func=get_remote_address)


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"]            = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///securechat.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"]    = int(os.getenv("MAX_FILE_SIZE_MB", 10)) * 1024 * 1024
    app.config["UPLOAD_FOLDER"]         = os.getenv("UPLOAD_FOLDER", "app/static/uploads")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    db.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"

    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
        max_http_buffer_size=10 * 1024 * 1024,
    )

    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()
        _seed_default_rooms()

    return app


def _seed_default_rooms():
    from app.models import Room
    defaults = [
        ("general", "General discussion", None),
        ("dev",     "Development talk",   None),
        ("ops",     "Operations",         None),
    ]
    for name, desc, pwd in defaults:
        if not Room.query.filter_by(name=name).first():
            r = Room(name=name, description=desc)
            if pwd:
                r.set_password(pwd)
            db.session.add(r)
    db.session.commit()
