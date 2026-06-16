from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from urllib.parse import urlparse

from .. import MODULE_ACCESS
from ..forms import LoginForm, SelfRegistrationForm, UserCreateForm, UserUpdateForm
from ..models import Attendance, Complaint, FoodReport, Task, User, db
from ..utils.decorators import roles_required


auth_bp = Blueprint("auth", __name__)


ROLE_ACTIONS = {
    "admin": [
        "Create and structure supervisor, worker, citizen, and NGO accounts",
        "Monitor attendance, complaints, tasks, and food distribution",
        "Assign or reassign supervisors, NGOs, and escalated work",
        "Review analytics and intervene in delayed cases",
    ],
    "supervisor": [
        "Monitor workers linked to your supervision",
        "Review complaints assigned to you",
        "Convert complaints into worker tasks",
        "Track worker attendance and perform override attendance when required",
    ],
    "worker": [
        "Register your face profile for attendance",
        "Mark attendance with face and location",
        "View assigned tasks from your supervisor",
        "Upload before and after task evidence and update progress",
    ],
    "citizen": [
        "Register independently",
        "Submit complaints with image or voice evidence",
        "Track complaint status and food reports you submitted",
    ],
    "ngo": [
        "Register independently",
        "Review food requests notified by the system",
        "Accept assigned food distribution requests",
        "Update collection and distribution progress",
    ],
}


def _user_label(user):
    return f"{user.name} ({user.role})"


def _admin_user():
    return User.query.filter_by(role="admin").order_by(User.id.asc()).first()


def _manager_choices(exclude_user_id=None):
    choices = [(0, "System / none")]
    supervisors = User.query.filter_by(role="supervisor").order_by(User.name.asc()).all()
    admins = User.query.filter_by(role="admin").order_by(User.name.asc()).all()
    for user in supervisors + admins:
        if exclude_user_id and user.id == exclude_user_id:
            continue
        choices.append((user.id, _user_label(user)))
    return choices


def _manager_catalog(exclude_user_id=None):
    def _serialize(users):
        rows = []
        for user in users:
            if exclude_user_id and user.id == exclude_user_id:
                continue
            rows.append({"id": user.id, "label": _user_label(user)})
        return rows

    return {
        "admins": _serialize(User.query.filter_by(role="admin").order_by(User.name.asc()).all()),
        "supervisors": _serialize(User.query.filter_by(role="supervisor").order_by(User.name.asc()).all()),
    }


def _normalize_manager_id(role, managed_by_id):
    managed_by_id = managed_by_id or None
    if role == "worker":
        manager = db.session.get(User, managed_by_id) if managed_by_id else None
        if not manager or manager.role != "supervisor":
            return None, "Worker accounts must report to a supervisor."
        return manager.id, None
    if role in {"supervisor", "ngo"}:
        if managed_by_id is None:
            managed_by_id = current_user.id
        manager = db.session.get(User, managed_by_id)
        if not manager or manager.role != "admin":
            return None, "Supervisors and NGOs must report to an admin."
        return manager.id, None
    return None, None


def _user_delete_blockers(user):
    blockers = []
    if user.managed_users:
        blockers.append("reassign or remove managed users first")
    if user.attendance_records:
        blockers.append("attendance history exists")
    if user.created_tasks or user.assigned_tasks:
        blockers.append("task records exist")
    if user.complaints or user.assigned_complaints:
        blockers.append("complaint workflow records exist")
    if user.reported_food or user.accepted_food:
        blockers.append("food workflow records exist")
    return blockers


def _safe_next_url(next_url):
    if not next_url:
        return None
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return None
    if not next_url.startswith("/"):
        return None
    return next_url


@auth_bp.route("/", methods=["GET"])
def index():
    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            next_url = _safe_next_url(request.args.get("next"))
            flash("Signed in successfully.", "success")
            return redirect(next_url or url_for("auth.dashboard"))
        flash("Invalid email or password.", "danger")

    return render_template("login.html", form=form)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard"))

    form = SelfRegistrationForm()
    if form.validate_on_submit():
        admin = _admin_user()
        managed_by_id = admin.id if admin and form.role.data == "ngo" else None
        user = User(
            name=form.name.data.strip(),
            email=form.email.data.lower().strip(),
            role=form.role.data,
            managed_by_id=managed_by_id,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Account created successfully. You can sign in now.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html", form=form)


@auth_bp.route("/guide")
def role_guide():
    role_flows = {
        "admin": {
            "purpose": "Top-level controller for municipal operations and hierarchy management.",
            "actions": [
                "Creates supervisors and workers",
                "Monitors all attendance and task execution",
                "Reassigns complaints or food requests when needed",
                "Handles escalations and overrides decisions",
            ],
        },
        "supervisor": {
            "purpose": "Middle management role responsible for workers under their control.",
            "actions": [
                "Views worker attendance and can mark override attendance",
                "Receives assigned complaints",
                "Converts complaints into worker tasks",
                "Reviews completed worker tasks",
            ],
        },
        "worker": {
            "purpose": "Execution role for field work and attendance-driven accountability.",
            "actions": [
                "Logs in using admin-created account",
                "Registers face profile after first login",
                "Marks attendance with face + GPS/location",
                "Uploads before and after evidence for tasks",
            ],
        },
        "citizen": {
            "purpose": "External civic participant for complaints and food reporting.",
            "actions": [
                "Self-registers independently",
                "Submits complaints with optional media",
                "Reports food availability when needed",
                "Tracks the status of submitted records",
            ],
        },
        "ngo": {
            "purpose": "Support role for food collection and distribution.",
            "actions": [
                "Self-registers independently",
                "Receives food notifications from the system",
                "Accepts distribution requests",
                "Updates collection and final distribution status",
            ],
        },
    }
    return render_template("role_guide.html", role_flows=role_flows)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    stats = {
        "total_users": User.query.count(),
        "attendance_today": Attendance.query.filter(db.func.date(Attendance.timestamp) == db.func.current_date()).count(),
        "open_tasks": Task.query.filter(Task.status.in_(["Assigned", "In Progress", "Completed"])).count(),
        "open_complaints": Complaint.query.filter(Complaint.status != "Resolved").count(),
        "food_reports": FoodReport.query.count(),
    }

    assigned_tasks = []
    if current_user.role == "worker":
        assigned_tasks = (
            Task.query.filter_by(assigned_to_id=current_user.id)
            .order_by(Task.deadline.asc())
            .limit(5)
            .all()
        )
    elif current_user.role == "supervisor":
        worker_ids = [worker.id for worker in current_user.managed_workers]
        conditions = [Task.created_by_id == current_user.id, Task.assigned_to_id == current_user.id]
        if worker_ids:
            conditions.append(Task.assigned_to_id.in_(worker_ids))
        assigned_tasks = Task.query.filter(or_(*conditions)).order_by(Task.deadline.asc()).limit(5).all()

    dashboard_panels = {
        "recent_attendance": current_user.role in {"admin", "supervisor", "worker"},
        "recent_complaints": current_user.role in {"admin", "supervisor", "citizen"},
        "recent_food_reports": current_user.role in {"admin", "supervisor", "citizen", "ngo"},
        "assigned_tasks": current_user.role in {"worker", "supervisor"},
    }

    if current_user.role == "citizen":
        recent_complaints = Complaint.query.filter_by(user_id=current_user.id).order_by(Complaint.created_at.desc()).limit(5).all()
        recent_food_reports = FoodReport.query.filter_by(created_by_id=current_user.id).order_by(FoodReport.created_at.desc()).limit(5).all()
    elif current_user.role == "supervisor":
        recent_complaints = (
            Complaint.query.filter_by(assigned_supervisor_id=current_user.id)
            .order_by(Complaint.created_at.desc())
            .limit(5)
            .all()
        )
        recent_food_reports = FoodReport.query.order_by(FoodReport.created_at.desc()).limit(5).all()
    elif current_user.role == "ngo":
        recent_complaints = []
        recent_food_reports = (
            FoodReport.query.filter(
                (FoodReport.assigned_ngo_id == current_user.id) | (FoodReport.assigned_ngo_id.is_(None))
            )
            .order_by(FoodReport.created_at.desc())
            .limit(5)
            .all()
        )
    elif current_user.role == "worker":
        recent_complaints = []
        recent_food_reports = []
    else:
        recent_complaints = Complaint.query.order_by(Complaint.created_at.desc()).limit(5).all()
        recent_food_reports = FoodReport.query.order_by(FoodReport.created_at.desc()).limit(5).all()

    if current_user.role == "worker":
        recent_attendance = (
            Attendance.query.filter_by(user_id=current_user.id)
            .order_by(Attendance.timestamp.desc())
            .limit(5)
            .all()
        )
    else:
        recent_attendance = Attendance.query.order_by(Attendance.timestamp.desc()).limit(5).all()

    return render_template(
        "dashboard.html",
        stats=stats,
        assigned_tasks=assigned_tasks,
        recent_complaints=recent_complaints,
        recent_food_reports=recent_food_reports,
        recent_attendance=recent_attendance,
        role_actions=ROLE_ACTIONS,
        module_access=MODULE_ACCESS,
        dashboard_panels=dashboard_panels,
    )


@auth_bp.route("/admin/users", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def manage_users():
    form = UserCreateForm()
    form.managed_by.choices = _manager_choices()

    if form.validate_on_submit():
        managed_by_id, manager_error = _normalize_manager_id(form.role.data, form.managed_by.data)
        if manager_error:
            form.managed_by.errors.append(manager_error)
            users = User.query.order_by(User.role.asc(), User.name.asc()).all()
            return render_template("admin_users.html", form=form, users=users, manager_catalog=_manager_catalog())

        user = User(
            name=form.name.data.strip(),
            email=form.email.data.lower().strip(),
            role=form.role.data,
            managed_by_id=managed_by_id,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("User account created successfully.", "success")
        return redirect(url_for("auth.manage_users"))

    users = User.query.order_by(User.role.asc(), User.name.asc()).all()
    return render_template("admin_users.html", form=form, users=users, manager_catalog=_manager_catalog())


@auth_bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserUpdateForm(original_user=user)
    form.managed_by.choices = _manager_choices(exclude_user_id=user.id)

    if request.method == "GET":
        form.name.data = user.name
        form.email.data = user.email
        form.role.data = user.role
        form.managed_by.data = user.managed_by_id or 0

    if form.validate_on_submit():
        if user.id == current_user.id and form.role.data != "admin":
            form.role.errors.append("You cannot remove the admin role from the current signed-in account.")
            return render_template("admin_user_edit.html", form=form, user=user, manager_catalog=_manager_catalog(user.id))

        managed_by_id, manager_error = _normalize_manager_id(form.role.data, form.managed_by.data)
        if manager_error:
            form.managed_by.errors.append(manager_error)
            return render_template("admin_user_edit.html", form=form, user=user, manager_catalog=_manager_catalog(user.id))

        if user.managed_users and form.role.data != user.role:
            form.role.errors.append("Reassign managed users before changing this account role.")
            return render_template("admin_user_edit.html", form=form, user=user, manager_catalog=_manager_catalog(user.id))

        user.name = form.name.data.strip()
        user.email = form.email.data.lower().strip()
        user.role = form.role.data
        user.managed_by_id = managed_by_id
        if form.password.data:
            user.set_password(form.password.data)
        if form.clear_face_profile.data:
            user.face_embedding = None
        db.session.commit()
        flash("User updated successfully.", "success")
        return redirect(url_for("auth.manage_users"))

    return render_template("admin_user_edit.html", form=form, user=user, manager_catalog=_manager_catalog(user.id))


@auth_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@roles_required("admin")
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete the currently signed-in admin account.", "danger")
        return redirect(url_for("auth.manage_users"))

    blockers = _user_delete_blockers(user)
    if blockers:
        flash(f"User cannot be deleted yet: {', '.join(blockers)}.", "warning")
        return redirect(url_for("auth.manage_users"))

    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("auth.manage_users"))
