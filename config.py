import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration. Reads secrets from environment where possible
    so no credentials are hard-coded in source control (NFR-01)."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'plc_attendance.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Business rule: how long a check-in token stays valid after a session opens
    SESSION_WINDOW_MINUTES = int(os.environ.get("SESSION_WINDOW_MINUTES", 30))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
