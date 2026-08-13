import math
import random
import string
from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="teacher")  # 'admin' | 'teacher'
    department = db.Column(db.String(120), nullable=True)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sessions_created = db.relationship(
        "PLCSession", backref="creator", lazy=True, cascade="all, delete-orphan"
    )
    attendance_records = db.relationship(
        "Attendance", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    # --- password helpers (NFR-01: bcrypt/werkzeug hashing, never store plaintext) ---
    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.email} ({self.role}) approved={self.is_approved}>"


class PLCSession(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(120), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    access_code = db.Column(db.String(4), nullable=False)  # FR-03: rolling 4-digit token
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # --- Geolocation Coordinates & Margin Limit (meters) ---
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    radius_meters = db.Column(db.Float, nullable=False, default=150.0)

    attendance = db.relationship(
        "Attendance", backref="session", lazy=True, cascade="all, delete-orphan"
    )

    @staticmethod
    def generate_access_code() -> str:
        return "".join(random.choices(string.digits, k=4))

    def window_expires_at(self, window_minutes: int) -> datetime:
        return self.opened_at + timedelta(minutes=window_minutes)

    def is_within_window(self, window_minutes: int) -> bool:
        return self.is_active and datetime.utcnow() <= self.window_expires_at(window_minutes)

    def calculate_distance_meters(self, user_lat: float, user_lng: float) -> float:
        """Calculates distance between session venue coordinates and user location using Haversine formula."""
        if self.latitude is None or self.longitude is None or user_lat is None or user_lng is None:
            return 0.0
        r_earth = 6371000.0  # Earth's radius in meters
        phi1 = math.radians(self.latitude)
        phi2 = math.radians(user_lat)
        delta_phi = math.radians(user_lat - self.latitude)
        delta_lambda = math.radians(user_lng - self.longitude)

        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r_earth * c

    def is_within_geofence(self, user_lat: float, user_lng: float) -> tuple[bool, float]:
        """Returns (is_valid, distance_meters). If no session GPS is recorded, geofence is open."""
        if self.latitude is None or self.longitude is None or user_lat is None or user_lng is None:
            return True, 0.0
        distance = self.calculate_distance_meters(user_lat, user_lng)
        return distance <= self.radius_meters, distance

    def close(self):
        self.is_active = False
        self.closed_at = datetime.utcnow()

    def __repr__(self):
        return f"<PLCSession {self.title} code={self.access_code} active={self.is_active}>"


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint("session_id", "user_id", name="uq_session_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    check_in_timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Present")  # Present|Late|Absent

    # --- Anti-Proxy Device Fingerprint & Verified Geolocation ---
    device_id = db.Column(db.String(128), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    distance_meters = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return f"<Attendance session={self.session_id} user={self.user_id} device={self.device_id} status={self.status}>"
