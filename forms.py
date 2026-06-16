from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, DateField, HiddenField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError

from .models import COMPLAINT_STATUSES, FOOD_STATUSES, TASK_STATUSES, User


ROLE_CHOICES = [
    ("admin", "Admin"),
    ("supervisor", "Supervisor"),
    ("worker", "Worker"),
    ("citizen", "Citizen"),
    ("ngo", "NGO"),
]

PUBLIC_ROLE_CHOICES = [
    ("citizen", "Citizen"),
    ("ngo", "NGO"),
]

ATTENDANCE_REQUIRED_ROLES = {"worker"}


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    submit = SubmitField("Sign In")


class UserCreateForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    managed_by = SelectField("Reports to / Managed by", coerce=int, validators=[Optional()], validate_choice=False)
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create User")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower().strip()).first():
            raise ValidationError("Email is already registered.")

    def validate(self, extra_validators=None):
        is_valid = super().validate(extra_validators=extra_validators)
        if not is_valid:
            return False
        if self.role.data == "worker" and not self.managed_by.data:
            self.managed_by.errors.append("Worker accounts must be linked to a supervisor.")
            return False
        return True


class SelfRegistrationForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    role = SelectField("Register as", choices=PUBLIC_ROLE_CHOICES, validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create Account")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower().strip()).first():
            raise ValidationError("Email is already registered.")


class UserUpdateForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    managed_by = SelectField("Reports to / Managed by", coerce=int, validators=[Optional()], validate_choice=False)
    password = PasswordField("New password", validators=[Optional(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[Optional(), EqualTo("password", message="Passwords must match.")],
    )
    clear_face_profile = BooleanField("Clear saved face profile")
    submit = SubmitField("Save Changes")

    def __init__(self, original_user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_user = original_user

    def validate_email(self, field):
        email = field.data.lower().strip()
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and (not self.original_user or existing_user.id != self.original_user.id):
            raise ValidationError("Email is already registered.")

    def validate(self, extra_validators=None):
        is_valid = super().validate(extra_validators=extra_validators)
        if not is_valid:
            return False
        if self.role.data == "worker" and not self.managed_by.data:
            self.managed_by.errors.append("Worker accounts must be linked to a supervisor.")
            return False
        return True


class FaceRegistrationForm(FlaskForm):
    image = FileField("Face image", validators=[FileAllowed(["jpg", "jpeg", "png"], "Use JPG or PNG.")])
    captured_image = HiddenField("Captured webcam image")
    submit = SubmitField("Register Face")

    def validate(self, extra_validators=None):
        is_valid = super().validate(extra_validators=extra_validators)
        if not is_valid:
            return False
        has_file = bool(self.image.data and getattr(self.image.data, "filename", ""))
        has_capture = bool((self.captured_image.data or "").strip())
        if not has_file and not has_capture:
            self.image.errors.append("Upload an image or capture a live image from the webcam.")
            return False
        return True


class AttendanceForm(FlaskForm):
    location = StringField("GPS / Location", validators=[DataRequired(), Length(max=255)])
    image = FileField("Live face capture", validators=[FileAllowed(["jpg", "jpeg", "png"], "Use JPG or PNG.")])
    captured_image = HiddenField("Captured webcam image")
    submit = SubmitField("Mark Attendance")

    def validate(self, extra_validators=None):
        is_valid = super().validate(extra_validators=extra_validators)
        if not is_valid:
            return False
        has_file = bool(self.image.data and getattr(self.image.data, "filename", ""))
        has_capture = bool((self.captured_image.data or "").strip())
        if not has_file and not has_capture:
            self.image.errors.append("Upload an image or capture a live image from the webcam.")
            return False
        return True


class AttendanceOverrideForm(FlaskForm):
    worker_id = SelectField("Worker", coerce=int, validators=[DataRequired()], validate_choice=False)
    location = StringField("Location", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Mark Override Attendance")


class TaskForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=150)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=10)])
    location = StringField("Location", validators=[DataRequired(), Length(max=255)])
    assigned_to = SelectField("Assign to", coerce=int, validators=[DataRequired()], validate_choice=False)
    deadline = DateField("Deadline", validators=[DataRequired()])
    submit = SubmitField("Create Task")

    def validate_deadline(self, field):
        if field.data < date.today():
            raise ValidationError("Deadline cannot be in the past.")


class TaskProgressForm(FlaskForm):
    status = SelectField("Status", choices=[(status, status) for status in TASK_STATUSES], validators=[DataRequired()], validate_choice=False)
    before_image = FileField("Before image", validators=[FileAllowed(["jpg", "jpeg", "png"], "Use JPG or PNG.")])
    after_image = FileField("After image", validators=[FileAllowed(["jpg", "jpeg", "png"], "Use JPG or PNG.")])
    submit = SubmitField("Update")


class ComplaintForm(FlaskForm):
    description = TextAreaField("Issue description", validators=[DataRequired(), Length(min=10)])
    location = StringField("Location", validators=[DataRequired(), Length(max=255)])
    image = FileField("Upload image", validators=[FileAllowed(["jpg", "jpeg", "png"], "Use JPG or PNG.")])
    voice = FileField("Upload voice note", validators=[FileAllowed(["mp3", "wav", "m4a"], "Use MP3, WAV, or M4A.")])
    submit = SubmitField("Submit Complaint")


class ComplaintAssignmentForm(FlaskForm):
    supervisor_id = SelectField("Assign supervisor", coerce=int, validators=[DataRequired()], validate_choice=False)
    submit = SubmitField("Assign")


class ComplaintTaskForm(FlaskForm):
    title = StringField("Task title", validators=[DataRequired(), Length(max=150)])
    location = StringField("Task location", validators=[DataRequired(), Length(max=255)])
    assigned_to = SelectField("Assign worker", coerce=int, validators=[DataRequired()], validate_choice=False)
    deadline = DateField("Deadline", validators=[DataRequired()])
    submit = SubmitField("Convert To Task")

    def validate_deadline(self, field):
        if field.data < date.today():
            raise ValidationError("Deadline cannot be in the past.")


class ComplaintStatusForm(FlaskForm):
    status = SelectField(
        "Status",
        choices=[(status, status) for status in COMPLAINT_STATUSES],
        validators=[DataRequired()],
        validate_choice=False,
    )
    submit = SubmitField("Update Status")


class FoodReportForm(FlaskForm):
    quantity = StringField("Quantity", validators=[DataRequired(), Length(max=120)])
    location = StringField("Location", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Report Food Availability")


class FoodAssignForm(FlaskForm):
    ngo_id = SelectField("Assign NGO", coerce=int, validators=[DataRequired()], validate_choice=False)
    submit = SubmitField("Assign NGO")


class FoodStatusForm(FlaskForm):
    status = SelectField(
        "Status",
        choices=[(status, status) for status in FOOD_STATUSES],
        validators=[DataRequired()],
        validate_choice=False,
    )
    submit = SubmitField("Update Status")
