import hashlib
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, PLCSession, Attendance
from forms import RegisterForm, LoginForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = RegisterForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if existing:
            flash("An account with that email already exists.", "danger")
            return render_template("auth/register.html", form=form)

        user = User(
            name=form.name.data.strip(),
            email=form.email.data.lower().strip(),
            department=form.department.data.strip() if form.department.data else None,
            role=form.role.data,
            is_approved=False,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash(
            "Account registered successfully! Your account is pending administrator approval before you can log in.",
            "info",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.check_password(form.password.data):
            if not user.is_approved:
                flash(
                    "Your account is pending administrator approval. Please contact your PLC coordinator.",
                    "warning",
                )
                return render_template("auth/login.html", form=form)

            # Prevent device from logging in with different credentials if it already submitted for an active session
            device_id = form.device_id.data.strip() if (form.device_id.data and form.device_id.data.strip()) else None
            if device_id and not user.is_admin:
                active_proxy_attendance = (
                    Attendance.query.join(PLCSession)
                    .filter(
                        PLCSession.is_active == True,
                        Attendance.device_id == device_id,
                        Attendance.user_id != user.id,
                    )
                    .first()
                )
                if active_proxy_attendance:
                    flash(
                        "You can't submit twice. This device has already been used to record attendance for another educator.",
                        "danger",
                    )
                    return render_template("auth/login.html", form=form)

            login_user(user)
            flash(f"Welcome back, {user.name.split()[0]}.", "success")
            return redirect(url_for("admin.dashboard") if user.is_admin else url_for("teacher.dashboard"))
        flash("Incorrect email or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("auth.login"))
