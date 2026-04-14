from datetime import datetime
from flask_login import UserMixin
from app import db, bcrypt


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(32), unique=True, nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password   = db.Column(db.String(128), nullable=False)
    avatar     = db.Column(db.String(2), default="?")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages   = db.relationship("Message", backref="author", lazy=True)

    def set_password(self, raw):
        self.password = bcrypt.generate_password_hash(raw).decode("utf-8")

    def check_password(self, raw):
        return bcrypt.check_password_hash(self.password, raw)

    def to_dict(self):
        return {"id": self.id, "username": self.username, "avatar": self.avatar}


class Room(db.Model):
    __tablename__ = "rooms"
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(32), unique=True, nullable=False)
    description = db.Column(db.String(120), default="")
    password    = db.Column(db.String(128), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    messages    = db.relationship("Message", backref="room", lazy=True, cascade="all, delete")

    def set_password(self, raw):
        self.password = bcrypt.generate_password_hash(raw).decode("utf-8")

    def check_password(self, raw):
        if not self.password:
            return True
        return bcrypt.check_password_hash(self.password, raw)

    @property
    def is_private(self):
        return self.password is not None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "private": self.is_private,
        }


class Message(db.Model):
    __tablename__ = "messages"
    id         = db.Column(db.Integer, primary_key=True)
    content    = db.Column(db.Text, nullable=False)       # encrypted ciphertext
    iv         = db.Column(db.String(64), nullable=False)  # AES IV for E2E
    msg_type   = db.Column(db.String(16), default="text") # text | file
    file_url   = db.Column(db.String(256), nullable=True)
    file_name  = db.Column(db.String(128), nullable=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    room_id    = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":        self.id,
            "content":   self.content,
            "iv":        self.iv,
            "type":      self.msg_type,
            "file_url":  self.file_url,
            "file_name": self.file_name,
            "username":  self.author.username,
            "avatar":    self.author.avatar,
            "time":      self.created_at.strftime("%H:%M"),
            "date":      self.created_at.strftime("%Y-%m-%d"),
        }
