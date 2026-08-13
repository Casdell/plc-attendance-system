from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, IntegerField, FloatField, HiddenField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange, Optional


class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(check_deliverability=False), Length(max=160)],
    )
    department = StringField("Department", validators=[Length(max=120)])
    role = SelectField(
        "Role",
        choices=[("teacher", "Teacher"), ("admin", "Administrator / PLC Coordinator")],
        validators=[DataRequired()],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(check_deliverability=False)])
    password = PasswordField("Password", validators=[DataRequired()])
    device_id = HiddenField("Device ID", validators=[Optional()])
    submit = SubmitField("Log in")


class SessionForm(FlaskForm):
    title = StringField("Session title", validators=[DataRequired(), Length(max=200)])
    department = StringField("Department", validators=[Length(max=120)])
    duration_minutes = IntegerField(
        "Duration (minutes)",
        default=60,
        validators=[DataRequired(), NumberRange(min=5, max=480)],
    )
    # Venue Geolocation Coordinates & Geofence Radius
    latitude = FloatField("Venue Latitude", validators=[Optional()])
    longitude = FloatField("Venue Longitude", validators=[Optional()])
    radius_meters = FloatField(
        "Geofence Radius (meters)",
        default=1000.0,
        validators=[Optional(), NumberRange(min=10.0, max=50000.0)],
    )
    submit = SubmitField("Open session")


class CheckInForm(FlaskForm):
    access_code = StringField(
        "4-digit verification code",
        validators=[DataRequired(), Length(min=4, max=4, message="Enter the 4-digit code.")],
    )
    # Anti-Proxy Device Fingerprint & Coordinates
    device_id = HiddenField("Device Fingerprint ID", validators=[Optional()])
    latitude = HiddenField("Teacher Latitude", validators=[Optional()])
    longitude = HiddenField("Teacher Longitude", validators=[Optional()])
    submit = SubmitField("Verify & check in")


class AdminResetPasswordForm(FlaskForm):
    new_password = PasswordField(
        "New Password",
        validators=[DataRequired(), Length(min=8, message="Password must be at least 8 characters long.")],
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")],
    )
    submit = SubmitField("Reset Password")
