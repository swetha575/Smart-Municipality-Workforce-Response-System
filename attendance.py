from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..forms import AttendanceForm, AttendanceOverrideForm, FaceRegistrationForm
from ..models import Attendance, User, db
from ..onnx_model.face_utils import (
    FaceRecognitionError,
    compare_embeddings,
    deserialize_embedding,
    generate_embedding,
    serialize_embedding,
)
from ..utils.decorators import roles_required
from ..utils.webcam import WebcamImageError, extract_image_bytes


attendance_bp = Blueprint("attendance", __name__)


def _visible_workers():
    if current_user.role == "admin":
        return User.query.filter_by(role="worker").order_by(User.name.asc()).all()
    if current_user.role == "supervisor":
        return User.query.filter_by(role="worker", managed_by_id=current_user.id).order_by(User.name.asc()).all()
    return []


def _visible_attendance_records():
    if current_user.role == "worker":
        return (
            Attendance.query.filter_by(user_id=current_user.id)
            .order_by(Attendance.timestamp.desc())
            .limit(20)
            .all()
        )
    worker_ids = [worker.id for worker in _visible_workers()]
    if current_user.role == "admin":
        return Attendance.query.order_by(Attendance.timestamp.desc()).limit(30).all()
    if worker_ids:
        return (
            Attendance.query.filter(Attendance.user_id.in_(worker_ids))
            .order_by(Attendance.timestamp.desc())
            .limit(30)
            .all()
        )
    return []


@attendance_bp.route("/", methods=["GET", "POST"])
@login_required
@roles_required("admin", "supervisor", "worker")
def index():
    registration_form = FaceRegistrationForm(prefix="register")
    attendance_form = AttendanceForm(prefix="mark")
    override_form = AttendanceOverrideForm(prefix="override")
    visible_workers = _visible_workers()
    override_form.worker_id.choices = [(worker.id, worker.name) for worker in visible_workers]

    if current_user.role == "worker" and registration_form.submit.data and registration_form.validate_on_submit():
        try:
            image_bytes = extract_image_bytes(registration_form.image.data, registration_form.captured_image.data)
            embedding = generate_embedding(image_bytes)
            current_user.face_embedding = serialize_embedding(embedding)
            db.session.commit()
            flash("Face profile registered successfully.", "success")
            return redirect(url_for("attendance.index"))
        except (FaceRecognitionError, WebcamImageError) as exc:
            flash(str(exc), "danger")

    if current_user.role == "worker" and attendance_form.submit.data and attendance_form.validate_on_submit():
        if not current_user.face_embedding:
            flash("Register your face profile before marking attendance.", "warning")
            return redirect(url_for("attendance.index"))

        existing_today = Attendance.query.filter(
            Attendance.user_id == current_user.id,
            db.func.date(Attendance.timestamp) == db.func.current_date(),
        ).first()
        if existing_today:
            flash("Attendance for today has already been marked.", "info")
            return redirect(url_for("attendance.index"))

        try:
            stored_embedding = deserialize_embedding(current_user.face_embedding)
            image_bytes = extract_image_bytes(attendance_form.image.data, attendance_form.captured_image.data)
            live_embedding = generate_embedding(image_bytes)
            is_match, similarity = compare_embeddings(
                stored_embedding,
                live_embedding,
                current_app.config["FACE_MATCH_THRESHOLD"],
            )
            if not is_match:
                flash(f"Face mismatch detected. Similarity score: {similarity:.2f}", "danger")
                return redirect(url_for("attendance.index"))

            record = Attendance(
                user_id=current_user.id,
                location=attendance_form.location.data.strip(),
                embedding=serialize_embedding(live_embedding),
                marked_by_id=current_user.id,
                is_override=False,
            )
            db.session.add(record)
            db.session.commit()
            flash("Attendance marked successfully.", "success")
            return redirect(url_for("attendance.index"))
        except (FaceRecognitionError, WebcamImageError) as exc:
            flash(str(exc), "danger")

    if current_user.role in {"admin", "supervisor"} and override_form.submit.data and override_form.validate_on_submit():
        worker = User.query.get_or_404(override_form.worker_id.data)
        if current_user.role == "supervisor" and worker.managed_by_id != current_user.id:
            flash("You can only mark override attendance for your own workers.", "danger")
            return redirect(url_for("attendance.index"))

        existing_today = Attendance.query.filter(
            Attendance.user_id == worker.id,
            db.func.date(Attendance.timestamp) == db.func.current_date(),
        ).first()
        if existing_today:
            flash("That worker already has an attendance record for today.", "info")
            return redirect(url_for("attendance.index"))

        record = Attendance(
            user_id=worker.id,
            location=override_form.location.data.strip(),
            embedding=worker.face_embedding or "OVERRIDE",
            marked_by_id=current_user.id,
            is_override=True,
        )
        db.session.add(record)
        db.session.commit()
        flash("Override attendance marked successfully.", "success")
        return redirect(url_for("attendance.index"))

    records = _visible_attendance_records()
    return render_template(
        "attendance.html",
        registration_form=registration_form,
        attendance_form=attendance_form,
        override_form=override_form,
        records=records,
        visible_workers=visible_workers,
    )
