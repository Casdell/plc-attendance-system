import hashlib
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from extensions import db
from models import PLCSession, Attendance
from forms import CheckInForm
from config import Config
from device import get_device_identifiers, is_device_blocked_for_session

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


@teacher_bp.route("/")
@login_required
def dashboard():
    active_sessions = PLCSession.query.filter_by(is_active=True).order_by(
        PLCSession.opened_at.desc()
    ).all()
    my_checkin_session_ids = {
        a.session_id for a in Attendance.query.filter_by(user_id=current_user.id).all()
    }
    return render_template(
        "teacher/dashboard.html",
        active_sessions=active_sessions,
        checked_in=my_checkin_session_ids,
        window_minutes=Config.SESSION_WINDOW_MINUTES,
    )


@teacher_bp.route("/sessions/<int:session_id>/checkin", methods=["GET", "POST"])
@login_required
def checkin(session_id):
    session_obj = PLCSession.query.get_or_404(session_id)
    form = CheckInForm()

    if form.validate_on_submit():
        # --- Multi-Stage Security Validation Logic ---

        # Check 1: Is the session currently active and within its time window?
        if not session_obj.is_within_window(Config.SESSION_WINDOW_MINUTES):
            flash("This session is closed or its check-in window has expired.", "danger")
            return redirect(url_for("teacher.dashboard"))

        # Check 2: Does the submitted token match the session's active 4-digit code?
        if form.access_code.data.strip() != session_obj.access_code:
            flash("Incorrect verification code. Please check the code shown at the venue.", "danger")
            return render_template("teacher/checkin.html", session_obj=session_obj, form=form)

        # Check 3: Has this teacher/user already checked in to this session?
        existing_user_record = Attendance.query.filter_by(
            session_id=session_obj.id, user_id=current_user.id
        ).first()
        if existing_user_record:
            flash("You've already checked in to this session.", "info")
            if current_user.is_admin:
                return redirect(url_for("admin.session_detail", session_id=session_obj.id))
            return redirect(url_for("teacher.dashboard"))

        # Check 4: Anti-Proxy Device Lock (Single-Device-Per-Session)
        canonical_dev, candidate_devs = get_device_identifiers(request, form)

        if is_device_blocked_for_session(session_obj.id, candidate_devs, current_user.id):
            flash(
                "You can't submit twice. This device has already recorded attendance for another attendee in this session.",
                "danger",
            )
            return render_template("teacher/checkin.html", session_obj=session_obj, form=form)

        # Check 5: Venue GPS Geofencing Margin Check
        user_lat = None
        user_lng = None
        distance_meters = 0.0

        if form.latitude.data and form.longitude.data:
            try:
                user_lat = float(form.latitude.data)
                user_lng = float(form.longitude.data)
            except (ValueError, TypeError):
                user_lat = None
                user_lng = None

        if session_obj.latitude is not None and session_obj.longitude is not None:
            if user_lat is not None and user_lng is not None:
                is_inside, distance_meters = session_obj.is_within_geofence(user_lat, user_lng)
                if not is_inside:
                    flash(
                        f"Geofence Verification Failed: You must be physically present within {int(session_obj.radius_meters)} meters of the venue. Your current distance is approximately {int(distance_meters)} meters.",
                        "danger",
                    )
                    return render_template("teacher/checkin.html", session_obj=session_obj, form=form)

        # Persistence: All cryptographic, device, and geofence checks passed
        record = Attendance(
            session_id=session_obj.id,
            user_id=current_user.id,
            status="Present",
            device_id=canonical_dev,
            latitude=user_lat,
            longitude=user_lng,
            distance_meters=distance_meters,
        )
        db.session.add(record)
        db.session.commit()
        flash(f'Checked in to "{session_obj.title}". Attendance verified and recorded.', "success")

        dest_url = url_for("admin.session_detail", session_id=session_obj.id) if current_user.is_admin else url_for("teacher.dashboard")
        response = redirect(dest_url)
        response.set_cookie("plc_device_id", canonical_dev, max_age=31536000, samesite="Lax")
        return response

    elif request.method == "POST":
        err_msgs = [err for field in form.errors.values() for err in field]
        if err_msgs:
            flash(f"Verification Failed: {'; '.join(err_msgs)}", "danger")
        else:
            flash("Verification Failed: Please enter a valid 4-digit code and ensure device ID is present.", "danger")

    return render_template("teacher/checkin.html", session_obj=session_obj, form=form)


@teacher_bp.route("/history")
@login_required
def history():
    records = (
        Attendance.query.filter_by(user_id=current_user.id)
        .order_by(Attendance.check_in_timestamp.desc())
        .all()
    )
    return render_template("teacher/history.html", records=records)
