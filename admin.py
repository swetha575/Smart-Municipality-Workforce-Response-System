from flask import Blueprint, render_template
from flask_login import login_required

from ..forms import ATTENDANCE_REQUIRED_ROLES
from ..models import COMPLAINT_STATUSES, FOOD_STATUSES, TASK_STATUSES, Attendance, Complaint, FoodReport, Task, User
from ..utils.decorators import roles_required


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/analytics")
@login_required
@roles_required("admin")
def analytics():
    user_breakdown = {role: User.query.filter_by(role=role).count() for role in ["admin", "supervisor", "worker", "citizen", "ngo"]}
    task_breakdown = {status: Task.query.filter_by(status=status).count() for status in TASK_STATUSES}
    complaint_breakdown = {status: Complaint.query.filter_by(status=status).count() for status in COMPLAINT_STATUSES}
    food_breakdown = {status: FoodReport.query.filter_by(status=status).count() for status in FOOD_STATUSES}

    recent_attendance = Attendance.query.order_by(Attendance.timestamp.desc()).limit(10).all()
    worker_without_face = User.query.filter(User.role.in_(ATTENDANCE_REQUIRED_ROLES), User.face_embedding.is_(None)).count()
    return render_template(
        "analytics.html",
        user_breakdown=user_breakdown,
        task_breakdown=task_breakdown,
        complaint_breakdown=complaint_breakdown,
        food_breakdown=food_breakdown,
        recent_attendance=recent_attendance,
        worker_without_face=worker_without_face,
    )
