import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError

from ..models import User

COMMON = {"password", "password123", "123456789", "qwerty123", "iloveyou", "admin123", "letmein123",
          "welcome123", "uttarakhand", "garhwali123", "kumaoni123", "1234567890", "lokvaani123"}


def validate_password_strength(password: str, username: str = "", email: str = "") -> str | None:
    """Return a human-readable problem, or None when the password is acceptable."""
    if len(password) < 10:
        return "Use at least 10 characters."
    if len(password) > 128:
        return "Use at most 128 characters."
    if password.lower() in COMMON:
        return "That password is too common."
    if password.isdigit() or password.isalpha():
        return "Mix letters with numbers or symbols."
    low = password.lower()
    if username and len(username) >= 3 and username.lower() in low:
        return "The password must not contain your username."
    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in low:
        return "The password must not contain your email name."
    if re.fullmatch(r"(.)\1+", password):
        return "Avoid repeating a single character."
    return None


class RegisterForm(FlaskForm):
    display_name = StringField("Your name", validators=[DataRequired(), Length(2, 80)])
    username = StringField("Username", validators=[DataRequired(), Length(3, 40)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=254)])
    password = PasswordField("Password", validators=[DataRequired(), Length(10, 128)])
    confirm = PasswordField("Repeat password", validators=[DataRequired(), EqualTo("password", "Passwords do not match.")])
    want_to_contribute = BooleanField("I want to contribute recordings or stories")

    def validate_username(self, field):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", field.data or ""):
            raise ValidationError("Use letters, numbers, dot, dash or underscore only.")
        if User.query.filter(User.username.ilike(field.data)).first():
            raise ValidationError("That username is taken.")

    def validate_email(self, field):
        if User.query.filter_by(email=(field.data or "").strip().lower()).first():
            raise ValidationError("An account with this email already exists.")

    def validate_password(self, field):
        problem = validate_password_strength(field.data or "", self.username.data or "", self.email.data or "")
        if problem:
            raise ValidationError(problem)


class LoginForm(FlaskForm):
    identifier = StringField("Username or email", validators=[DataRequired(), Length(max=254)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Keep me signed in on this device")


class ProfileForm(FlaskForm):
    display_name = StringField("Display name", validators=[DataRequired(), Length(2, 80)])
    bio = TextAreaField("About you", validators=[Optional(), Length(max=500)])


class ChangePasswordForm(FlaskForm):
    current = PasswordField("Current password", validators=[DataRequired()])
    new = PasswordField("New password", validators=[DataRequired(), Length(10, 128)])
    confirm = PasswordField("Repeat new password", validators=[DataRequired(), EqualTo("new", "Passwords do not match.")])
