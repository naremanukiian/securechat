import os
import uuid
import html
from datetime import datetime
from flask import (Blueprint, render_template, request, session,
                   redirect, url_for, jsonify, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from flask_socketio import emit, join_room, leave_room
from werkzeug.utils import secure_filename
from app import db, socketio, limiter
from app.models import User, Room, Message

main = Blueprint("main", __name__)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "pdf", "txt", "zip", "mp4", "webm"}
active_users = {}   # sid -> user_id


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def sanitize(text):
    return html.escape(str(text).strip())[:2000]


# ── Pages ──────────────────────────────────────────────────────────────────────

@main.route("/")
@login_required
def index():
    rooms = Room.query.order_by(Room.name).all()
    return render_template("chat.html", user=current_user, rooms=rooms)


@main.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    error = None
    if request.method == "POST":
        username = sanitize(request.form.get("username", ""))
        email    = sanitize(request.form.get("email", ""))
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        if len(username) < 2:
            error = "Username must be at least 2 characters."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif User.query.filter_by(username=username).first():
            error = "Username already taken."
        elif User.query.filter_by(email=email).first():
            error = "Email already registered."
        else:
            user = User(username=username, email=email, avatar=username[0].upper())
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("main.index"))

    return render_template("register.html", error=error)


@main.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    error = None
    if request.method == "POST":
        username = sanitize(request.form.get("username", ""))
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("main.index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


# ── API ────────────────────────────────────────────────────────────────────────

@main.route("/api/rooms", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def create_room():
    data     = request.get_json()
    name     = sanitize(data.get("name", ""))
    desc     = sanitize(data.get("description", ""))
    password = data.get("password", "")

    if not name or len(name) < 2:
        return jsonify({"error": "Room name too short"}), 400
    if Room.query.filter_by(name=name).first():
        return jsonify({"error": "Room already exists"}), 400

    room = Room(name=name, description=desc)
    if password:
        room.set_password(password)
    db.session.add(room)
    db.session.commit()

    socketio.emit("room_created", room.to_dict(), broadcast=True)
    return jsonify(room.to_dict()), 201


@main.route("/api/rooms/<int:room_id>/join", methods=["POST"])
@login_required
def join_room_api(room_id):
    room = Room.query.get_or_404(room_id)
    data = request.get_json() or {}
    pwd  = data.get("password", "")
    if not room.check_password(pwd):
        return jsonify({"error": "Wrong room password"}), 403
    session[f"room_{room_id}"] = True
    return jsonify({"ok": True})


@main.route("/api/rooms/<int:room_id>/history")
@login_required
def room_history(room_id):
    if not session.get(f"room_{room_id}") and Room.query.get(room_id).is_private:
        return jsonify({"error": "Unauthorized"}), 403
    msgs = (Message.query
            .filter_by(room_id=room_id)
            .order_by(Message.created_at.desc())
            .limit(50).all())
    return jsonify([m.to_dict() for m in reversed(msgs)])


@main.route("/api/upload", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename or not allowed_file(f.filename):
        return jsonify({"error": "File type not allowed"}), 400

    ext      = f.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    f.save(os.path.join(upload_dir, filename))

    url = url_for("static", filename=f"uploads/{filename}")
    return jsonify({"url": url, "name": secure_filename(f.filename)})


@main.route("/health")
def health():
    return jsonify({"status": "ok", "users": len(active_users)})


# ── Socket.IO ──────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    if not current_user.is_authenticated:
        return False
    active_users[request.sid] = current_user.id
    emit("system", {
        "msg": f"{current_user.username} joined",
        "count": len(active_users)
    }, broadcast=True)


@socketio.on("disconnect")
def on_disconnect():
    uid = active_users.pop(request.sid, None)
    user = User.query.get(uid) if uid else None
    name = user.username if user else "Someone"
    emit("system", {"msg": f"{name} left", "count": len(active_users)}, broadcast=True)


@socketio.on("join")
def on_join(data):
    room_id = int(data.get("room_id", 0))
    room = Room.query.get(room_id)
    if not room:
        emit("error", {"msg": "Room not found"})
        return
    if room.is_private and not session.get(f"room_{room_id}"):
        emit("error", {"msg": "Enter room password first"})
        return
    join_room(str(room_id))
    emit("joined", {"room_id": room_id, "room_name": room.name})


@socketio.on("leave")
def on_leave(data):
    room_id = str(data.get("room_id", ""))
    leave_room(room_id)


@socketio.on("message")
def on_message(data):
    room_id  = int(data.get("room_id", 0))
    content  = sanitize(data.get("content", ""))
    iv       = sanitize(data.get("iv", ""))
    msg_type = data.get("type", "text")
    file_url  = data.get("file_url")
    file_name = data.get("file_name")

    if not content or not iv:
        return

    room = Room.query.get(room_id)
    if not room:
        return
    if room.is_private and not session.get(f"room_{room_id}"):
        return

    msg = Message(
        content   = content,
        iv        = iv,
        msg_type  = msg_type,
        file_url  = file_url,
        file_name = file_name,
        user_id   = current_user.id,
        room_id   = room_id,
    )
    db.session.add(msg)
    db.session.commit()

    emit("message", msg.to_dict(), to=str(room_id))
