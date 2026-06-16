from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ..forms import ComplaintAssignmentForm, ComplaintForm, ComplaintStatusForm, ComplaintTaskForm
from ..models import Complaint, Task, User, db
from ..utils.decorators import roles_required


complaints_bp = Blueprint("complaints", __name__)


def _save_upload(file_storage, folder_name):
    if not file_storage or not file_storage.filename:
        return None
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]) / folder_name
    upload_root.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file_storage.filename)
    stored_name = f"{uuid4().hex}_{filename}"
    file_path = upload_root / stored_name
    file_storage.save(file_path)
    return str(Path("uploads") / folder_name / stored_name).replace("\\", "/")


def _delete_upload(relative_path):
    if not relative_path:
        return
    file_path = Path(current_app.static_folder) / relative_path
    if file_path.exists() and file_path.is_file():
        file_path.unlink()


def _available_supervisors():
    return User.query.filter_by(role="supervisor").order_by(User.name.asc()).all()


def _auto_assign_supervisor():
    supervisors = _available_supervisors()
    if not supervisors:
        return None
    workload = []
    for supervisor in supervisors:
        active_complaint_count = Complaint.query.filter(
            Complaint.assigned_supervisor_id == supervisor.id,
            Complaint.status.in_(["Assigned", "Task Created", "In Progress", "Escalated"]),
        ).count()
        workload.append((active_complaint_count, supervisor))
    workload.sort(key=lambda item: (item[0], item[1].name.lower()))
    return workload[0][1]


def _visible_complaints():
    if current_user.role == "citizen":
        return Complaint.query.filter_by(user_id=current_user.id).order_by(Complaint.created_at.desc()).all()
    if current_user.role == "supervisor":
        return Complaint.query.filter_by(assigned_supervisor_id=current_user.id).order_by(Complaint.created_at.desc()).all()
    return Complaint.query.order_by(Complaint.created_at.desc()).all()


def _workers_for_complaint(complaint):
    if current_user.role == "supervisor":
        supervisor = current_user
    else:
        supervisor = complaint.assigned_supervisor
    if not supervisor:
        return []
    return User.query.filter_by(role="worker", managed_by_id=supervisor.id).order_by(User.name.asc()).all()


@complaints_bp.route("/", methods=["GET", "POST"])
@login_required
@roles_required("admin", "supervisor", "citizen")
def index():
    form = ComplaintForm()
    if current_user.role == "citizen" and form.validate_on_submit():
        assigned_supervisor = _auto_assign_supervisor()
        complaint = Complaint(
            user_id=current_user.id,
            assigned_supervisor_id=assigned_supervisor.id if assigned_supervisor else None,
            description=form.description.data.strip(),
            image=_save_upload(form.image.data, "complaint_images"),
            voice=_save_upload(form.voice.data, "complaint_voice"),
            location=form.location.data.strip(),
            status="Assigned" if assigned_supervisor else "Submitted",
        )
        db.session.add(complaint)
        db.session.commit()
        if assigned_supervisor:
            flash(f"Complaint submitted and routed to supervisor {assigned_supervisor.name}.", "success")
        else:
            flash("Complaint submitted successfully. It is waiting for supervisor assignment.", "success")
        return redirect(url_for("complaints.index"))

    complaints = _visible_complaints()
    supervisors = _available_supervisors()
    complaint_workers = {complaint.id: _workers_for_complaint(complaint) for complaint in complaints}
    return render_template(
        "complaints.html",
        form=form,
        complaints=complaints,
        supervisors=supervisors,
        complaint_workers=complaint_workers,
    )


@complaints_bp.route("/<int:complaint_id>/assign", methods=["POST"])
@login_required
@roles_required("admin")
def assign_supervisor(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)
    form = ComplaintAssignmentForm()
    form.supervisor_id.choices = [(user.id, user.name) for user in _available_supervisors()]
    if form.validate_on_submit():
        complaint.assigned_supervisor_id = form.supervisor_id.data
        if complaint.status == "Submitted":
            complaint.status = "Assigned"
        db.session.commit()
        flash("Complaint assigned to supervisor.", "success")
    else:
        flash("Unable to assign complaint to supervisor.", "danger")
    return redirect(url_for("complaints.index"))


@complaints_bp.route("/<int:complaint_id>/create-task", methods=["POST"])
@login_required
@roles_required("admin", "supervisor")
def create_task(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)
    if current_user.role == "supervisor" and complaint.assigned_supervisor_id != current_user.id:
        flash("You can only convert complaints assigned to you.", "danger")
        return redirect(url_for("complaints.index"))

    form = ComplaintTaskForm()
    workers = _workers_for_complaint(complaint)
    form.assigned_to.choices = [(worker.id, worker.name) for worker in workers]

    if not workers:
        flash("No eligible workers are available under the assigned supervisor.", "warning")
        return redirect(url_for("complaints.index"))

    if form.validate_on_submit():
        if complaint.linked_task:
            flash("This complaint is already linked to a task.", "info")
            return redirect(url_for("complaints.index"))
        task = Task(
            title=form.title.data.strip(),
            description=complaint.description,
            location=form.location.data.strip(),
            assigned_to_id=form.assigned_to.data,
            created_by_id=current_user.id,
            complaint_id=complaint.id,
            status="Assigned",
            deadline=form.deadline.data,
        )
        complaint.status = "Task Created"
        db.session.add(task)
        db.session.commit()
        flash("Complaint converted to task and assigned to worker.", "success")
    else:
        flash("Unable to convert complaint to task.", "danger")
    return redirect(url_for("complaints.index"))


@complaints_bp.route("/<int:complaint_id>/status", methods=["POST"])
@login_required
@roles_required("admin", "supervisor")
def update_status(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)
    if current_user.role == "supervisor" and complaint.assigned_supervisor_id != current_user.id:
        flash("You can only update complaints assigned to you.", "danger")
        return redirect(url_for("complaints.index"))

    form = ComplaintStatusForm()
    if current_user.role == "admin":
        form.status.choices = [(status, status) for status in ["Assigned", "Resolved", "Escalated", "Rejected"]]
    else:
        form.status.choices = [(status, status) for status in ["Resolved", "Escalated", "Rejected"]]

    if form.validate_on_submit():
        complaint.status = form.status.data
        if complaint.linked_task and form.status.data == "Escalated":
            complaint.linked_task.status = "Escalated"
            complaint.linked_task.escalated = True
        db.session.commit()
        flash("Complaint status updated.", "success")
    else:
        flash("Unable to update complaint status.", "danger")
    return redirect(url_for("complaints.index"))


@complaints_bp.route("/<int:complaint_id>/delete", methods=["POST"])
@login_required
@roles_required("admin")
def delete_complaint(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)
    if complaint.linked_task:
        flash("Delete or unlink the related task before deleting this complaint.", "warning")
        return redirect(url_for("complaints.index"))

    _delete_upload(complaint.image)
    _delete_upload(complaint.voice)
    db.session.delete(complaint)
    db.session.commit()
    flash("Complaint deleted successfully.", "success")
    return redirect(url_for("complaints.index"))
