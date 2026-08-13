import csv
import io

from flask import Blueprint, render_template, redirect, url_for, flash, Response
from flask_login import login_required, current_user

from extensions import db
from models import PLCSession, User, Attendance
from forms import SessionForm, AdminResetPasswordForm
from decorators import admin_required
from config import Config

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    sessions = PLCSession.query.order_by(PLCSession.date.desc()).all()
    total_teachers = User.query.filter_by(role="teacher", is_approved=True).count()
    pending_users_count = User.query.filter_by(is_approved=False).count()
    return render_template(
        "admin/dashboard.html",
        sessions=sessions,
        total_teachers=total_teachers,
        pending_users_count=pending_users_count,
    )


@admin_bp.route("/sessions/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_session():
    form = SessionForm()
    if form.validate_on_submit():
        session_obj = PLCSession(
            title=form.title.data.strip(),
            department=form.department.data.strip() if form.department.data else None,
            duration_minutes=form.duration_minutes.data,
            access_code=PLCSession.generate_access_code(),
            creator_id=current_user.id,
            latitude=form.latitude.data,
            longitude=form.longitude.data,
            radius_meters=form.radius_meters.data if form.radius_meters.data else 150.0,
        )
        db.session.add(session_obj)
        db.session.commit()
        flash(f'Session "{session_obj.title}" opened. Code: {session_obj.access_code}', "success")
        return redirect(url_for("admin.session_detail", session_id=session_obj.id))

    return render_template("admin/session_form.html", form=form, is_edit=False)


@admin_bp.route("/sessions/<int:session_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_session(session_id):
    session_obj = PLCSession.query.get_or_404(session_id)
    form = SessionForm(obj=session_obj)
    if form.validate_on_submit():
        session_obj.title = form.title.data.strip()
        session_obj.department = form.department.data.strip() if form.department.data else None
        session_obj.duration_minutes = form.duration_minutes.data
        if form.latitude.data is not None:
            session_obj.latitude = form.latitude.data
        if form.longitude.data is not None:
            session_obj.longitude = form.longitude.data
        if form.radius_meters.data is not None:
            session_obj.radius_meters = form.radius_meters.data
        db.session.commit()
        flash(f'Session "{session_obj.title}" updated successfully.', "success")
        return redirect(url_for("admin.session_detail", session_id=session_obj.id))

    return render_template(
        "admin/session_form.html", form=form, session_obj=session_obj, is_edit=True
    )


@admin_bp.route("/sessions/<int:session_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_session(session_id):
    session_obj = PLCSession.query.get_or_404(session_id)
    title = session_obj.title
    db.session.delete(session_obj)
    db.session.commit()
    flash(f'Session "{title}" and its attendance records were deleted.', "info")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/sessions/<int:session_id>")
@login_required
@admin_required
def session_detail(session_id):
    session_obj = PLCSession.query.get_or_404(session_id)
    present_ids = {a.user_id for a in session_obj.attendance}
    teachers = User.query.filter_by(role="teacher").all()
    admin_attendees = User.query.filter(User.id.in_(present_ids), User.role != "teacher").all() if present_ids else []
    
    # Combined roster of all teachers + any coordinator/host who checked in
    present = [u for u in (teachers + admin_attendees) if u.id in present_ids]
    absent = [t for t in teachers if t.id not in present_ids]
    admin_checked_in = current_user.id in present_ids

    records_by_user = {a.user_id: a for a in session_obj.attendance}

    return render_template(
        "admin/session_detail.html",
        session_obj=session_obj,
        present=present,
        absent=absent,
        admin_checked_in=admin_checked_in,
        records_by_user=records_by_user,
        window_minutes=Config.SESSION_WINDOW_MINUTES,
    )


@admin_bp.route("/sessions/<int:session_id>/close", methods=["POST"])
@login_required
@admin_required
def close_session(session_id):
    session_obj = PLCSession.query.get_or_404(session_id)
    session_obj.close()
    db.session.commit()
    flash(f'Session "{session_obj.title}" closed.', "info")
    return redirect(url_for("admin.session_detail", session_id=session_obj.id))


@admin_bp.route("/sessions/<int:session_id>/manual-checkin/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def manual_checkin(session_id, user_id):
    session_obj = PLCSession.query.get_or_404(session_id)
    target_user = User.query.get_or_404(user_id)

    existing = Attendance.query.filter_by(session_id=session_obj.id, user_id=target_user.id).first()
    if existing:
        flash(f'Attendance for "{target_user.name}" has already been recorded.', "info")
    else:
        record = Attendance(
            session_id=session_obj.id,
            user_id=target_user.id,
            status="Present",
            device_id=f"Manual Override: Coordinator ({current_user.name})",
            latitude=session_obj.latitude,
            longitude=session_obj.longitude,
            distance_meters=0.0 if session_obj.latitude is not None else None,
        )
        db.session.add(record)
        db.session.commit()
        flash(f'Manual presence confirmed for "{target_user.name}".', "success")

    return redirect(url_for("admin.session_detail", session_id=session_obj.id))


@admin_bp.route("/sessions/<int:session_id>/revoke-checkin/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def revoke_checkin(session_id, user_id):
    session_obj = PLCSession.query.get_or_404(session_id)
    target_user = User.query.get_or_404(user_id)

    record = Attendance.query.filter_by(session_id=session_obj.id, user_id=target_user.id).first()
    if record:
        db.session.delete(record)
        db.session.commit()
        flash(f'Attendance record for "{target_user.name}" was revoked and marked absent.', "info")
    else:
        flash(f'No attendance record found for "{target_user.name}".', "warning")

    return redirect(url_for("admin.session_detail", session_id=session_obj.id))


@admin_bp.route("/sessions/<int:session_id>/export.csv")
@login_required
@admin_required
def export_csv(session_id):
    session_obj = PLCSession.query.get_or_404(session_id)
    present_ids = {a.user_id for a in session_obj.attendance}
    teachers = User.query.filter_by(role="teacher").all()
    admin_attendees = User.query.filter(User.id.in_(present_ids), User.role != "teacher").all() if present_ids else []
    all_roster = teachers + admin_attendees
    records_by_user = {a.user_id: a for a in session_obj.attendance}

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Name", "Email", "Department", "Role", "Status", "Check-in time", 
        "Device Fingerprint", "Verified Distance (m)", "Latitude", "Longitude"
    ])
    for u in all_roster:
        record = records_by_user.get(u.id)
        status = record.status if record else "Absent"
        check_in = record.check_in_timestamp.strftime("%Y-%m-%d %H:%M:%S") if record else "-"
        device = record.device_id if record and record.device_id else "-"
        dist = f"{record.distance_meters:.1f}" if record and record.distance_meters is not None else "-"
        lat = f"{record.latitude:.6f}" if record and record.latitude is not None else "-"
        lng = f"{record.longitude:.6f}" if record and record.longitude is not None else "-"
        writer.writerow([u.name, u.email, u.department or "-", u.role.title(), status, check_in, device, dist, lat, lng])

    filename = f"attendance_session_{session_obj.id}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# User Management & Administration
# ---------------------------------------------------------------------------

@admin_bp.route("/users")
@login_required
@admin_required
def users_list():
    users = User.query.order_by(User.created_at.desc()).all()
    pending_users = [u for u in users if not u.is_approved]
    active_teachers = [u for u in users if u.role == "teacher" and u.is_approved]
    admins = [u for u in users if u.role == "admin"]
    reset_form = AdminResetPasswordForm()

    return render_template(
        "admin/users.html",
        users=users,
        pending_users=pending_users,
        active_teachers=active_teachers,
        admins=admins,
        reset_form=reset_form,
    )


@admin_bp.route("/users/<int:user_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f'Account for "{user.name}" ({user.email}) has been approved and activated.', "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:user_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot reject your own account.", "danger")
        return redirect(url_for("admin.users_list"))
    name = user.name
    email = user.email
    db.session.delete(user)
    db.session.commit()
    flash(f'Registration request for "{name}" ({email}) was rejected and removed.', "info")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    form = AdminResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        db.session.commit()
        flash(f'Password for "{user.name}" ({user.email}) was successfully reset.', "success")
    else:
        error_msgs = "; ".join([e for err_list in form.errors.values() for e in err_list])
        flash(f"Failed to reset password: {error_msgs}", "danger")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Security Violation: You cannot delete your own active administrator account.", "danger")
        return redirect(url_for("admin.users_list"))

    name = user.name
    email = user.email
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{name}" ({email}) and all associated records have been permanently deleted.', "info")
    return redirect(url_for("admin.users_list"))
