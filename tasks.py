from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from ..forms import TaskForm, TaskProgressForm
from ..models import Complaint, Task, User, db
from ..utils.decorators import roles_required


tasks_bp = Blueprint("tasks", __name__)


def _save_task_image(file_storage, folder_name):
    if not file_storage or not file_storage.filename:
        return None
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]) / folder_name
    upload_root.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file_storage.filename)
    stored_name = f"{uuid4().hex}_{filename}"
    file_path = upload_root / stored_name
    file_storage.save(file_path)
    return str(Path("uploads") / folder_name / stored_name).replace("\\", "/")


def _delete_task_image(relative_path):
    if not relative_path:
        return
    file_path = Path(current_app.static_folder) / relative_path
    if file_path.exists() and file_path.is_file():
        file_path.unlink()


def _task_queryset():
    if current_user.role == "admin":
        return Task.query.order_by(Task.deadline.asc())
    if current_user.role == "supervisor":
        worker_ids = [worker.id for worker in current_user.managed_workers]
        conditions = [Task.created_by_id == current_user.id, Task.assigned_to_id == current_user.id]
        if worker_ids:
            conditions.append(Task.assigned_to_id.in_(worker_ids))
        return Task.query.filter(or_(*conditions)).order_by(Task.deadline.asc())
    return Task.query.filter_by(assigned_to_id=current_user.id).order_by(Task.deadline.asc())


def _assignable_users():
    if current_user.role == "admin":
        return User.query.filter_by(role="supervisor").order_by(User.name.asc()).all()
    if current_user.role == "supervisor":
        return User.query.filter_by(role="worker", managed_by_id=current_user.id).order_by(User.name.asc()).all()
    return []


@tasks_bp.route("/", methods=["GET", "POST"])
@login_required
@roles_required("admin", "supervisor", "worker")
def index():
    form = TaskForm()
    assignable_users = _assignable_users()
    form.assigned_to.choices = [(user.id, f"{user.name} ({user.role})") for user in assignable_users]

    can_create = current_user.role in {"admin", "supervisor"}

    if can_create and assignable_users and form.validate_on_submit():
        task = Task(
            title=form.title.data.strip(),
            description=form.description.data.strip(),
            location=form.location.data.strip(),
            assigned_to_id=form.assigned_to.data,
            created_by_id=current_user.id,
            deadline=form.deadline.data,
            status="Assigned",
        )
        db.session.add(task)
        db.session.commit()
        flash("Task created and assigned successfully.", "success")
        return redirect(url_for("tasks.index"))

    tasks = _task_queryset().all()
    assignment_target_label = "Supervisor" if current_user.role == "admin" else "Worker"
    return render_template(
        "tasks.html",
        form=form,
        tasks=tasks,
        can_create=can_create and bool(assignable_users),
        assignment_target_label=assignment_target_label,
    )


@tasks_bp.route("/<int:task_id>/status", methods=["POST"])
@login_required
@roles_required("admin", "supervisor", "worker")
def update_status(task_id):
    task = Task.query.get_or_404(task_id)
    is_assignee = task.assigned_to_id == current_user.id
    is_creator_or_admin = current_user.role == "admin" or task.created_by_id == current_user.id

    if not is_assignee and not is_creator_or_admin:
        flash("You do not have access to update this task.", "danger")
        return redirect(url_for("tasks.index"))

    form = TaskProgressForm()
    if is_assignee:
        form.status.choices = [("In Progress", "In Progress"), ("Completed", "Completed")]
    else:
        form.status.choices = [("Reviewed", "Reviewed"), ("Escalated", "Escalated")]

    if form.validate_on_submit():
        if current_user.role == "worker" and is_assignee:
            before_image = _save_task_image(form.before_image.data, "task_before")
            after_image = _save_task_image(form.after_image.data, "task_after")
            if before_image:
                _delete_task_image(task.before_image)
                task.before_image = before_image
            if after_image:
                _delete_task_image(task.after_image)
                task.after_image = after_image

            if form.status.data == "In Progress" and not task.before_image:
                flash("Worker must upload a before image when starting work.", "danger")
                return redirect(url_for("tasks.index"))
            if form.status.data == "Completed":
                if not task.before_image:
                    flash("Before image is required before completing the task.", "danger")
                    return redirect(url_for("tasks.index"))
                if not task.after_image:
                    flash("After image is required before completing the task.", "danger")
                    return redirect(url_for("tasks.index"))

        task.status = form.status.data
        task.escalated = form.status.data == "Escalated"

        if task.complaint:
            if task.status in {"In Progress", "Completed"}:
                task.complaint.status = "In Progress"
            elif task.status == "Reviewed":
                task.complaint.status = "Resolved"
            elif task.status == "Escalated":
                task.complaint.status = "Escalated"

        db.session.commit()
        flash("Task updated successfully.", "success")
    else:
        flash("Unable to update task status.", "danger")

    return redirect(url_for("tasks.index"))


@tasks_bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
@roles_required("admin")
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    linked_complaint = task.complaint

    _delete_task_image(task.before_image)
    _delete_task_image(task.after_image)

    if linked_complaint:
        linked_complaint.status = "Assigned" if linked_complaint.assigned_supervisor_id else "Submitted"

    db.session.delete(task)
    db.session.commit()
    flash("Task deleted successfully.", "success")
    return redirect(url_for("tasks.index"))
