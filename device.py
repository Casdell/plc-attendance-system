import hashlib
from flask import Request
from models import PLCSession, Attendance
from extensions import db


def get_device_identifiers(req: Request, form=None) -> tuple[str, list[str]]:
    """
    Extracts canonical and candidate device identifiers for the physical client.
    Never includes user_id in hardware fingerprints so physical devices are uniquely tracked.
    """
    candidates = []

    # 1. Check form device_id
    if form and hasattr(form, "device_id") and form.device_id.data:
        val = form.device_id.data.strip()
        if val:
            candidates.append(val)
            # If formatted as dev-UUID:entropy, also add the base UUID
            if ":" in val:
                base_uuid = val.split(":", 1)[0]
                if base_uuid and base_uuid not in candidates:
                    candidates.append(base_uuid)

    # 2. Check persistent browser cookie
    cookie_val = req.cookies.get("plc_device_id")
    if cookie_val:
        cookie_val = cookie_val.strip()
        if cookie_val and cookie_val not in candidates:
            candidates.append(cookie_val)
            if ":" in cookie_val:
                base_cookie = cookie_val.split(":", 1)[0]
                if base_cookie and base_cookie not in candidates:
                    candidates.append(base_cookie)

    # 3. Hardware / Browser Agent Fingerprint (Never uses user_id)
    ua = req.headers.get("User-Agent", "standard-browser")
    lang = req.headers.get("Accept-Language", "")
    ip = req.remote_addr or "127.0.0.1"
    # Group IP to /24 subnet for mobile networks if dynamic
    ip_parts = ip.split(".")
    ip_group = ".".join(ip_parts[:3]) if len(ip_parts) == 4 else ip
    hw_fingerprint = f"hw-{hashlib.sha256(f'{ua}:{lang}:{ip_group}'.encode()).hexdigest()[:24]}"
    if hw_fingerprint not in candidates:
        candidates.append(hw_fingerprint)

    # Canonical is first available candidate
    canonical = candidates[0]
    return canonical, candidates


def is_device_blocked_for_active_session(device_ids: list[str], user_id: int) -> bool:
    """
    Returns True if any active PLC session already has an attendance record from this device for another user.
    """
    if not device_ids:
        return False

    proxy_record = (
        Attendance.query.join(PLCSession)
        .filter(
            PLCSession.is_active == True,
            Attendance.device_id.in_(device_ids),
            Attendance.user_id != user_id,
        )
        .first()
    )
    return proxy_record is not None


def is_device_blocked_for_session(session_id: int, device_ids: list[str], user_id: int) -> bool:
    """
    Returns True if this specific session already has an attendance record from this device for another user.
    """
    if not device_ids:
        return False

    proxy_record = (
        Attendance.query.filter(
            Attendance.session_id == session_id,
            Attendance.device_id.in_(device_ids),
            Attendance.user_id != user_id,
        )
        .first()
    )
    return proxy_record is not None
