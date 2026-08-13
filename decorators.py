from functools import wraps
from flask import abort
from flask_login import current_user


def admin_required(f):
    """Enforces the Administrator role (NFR-01: prevent privilege escalation)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return decorated
