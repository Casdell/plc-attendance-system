from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User
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
