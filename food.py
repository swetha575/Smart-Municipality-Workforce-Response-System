from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..forms import FoodAssignForm, FoodReportForm, FoodStatusForm
from ..models import FoodReport, User, db
from ..utils.decorators import roles_required


food_bp = Blueprint("food", __name__)


def _available_ngos():
    return User.query.filter_by(role="ngo").order_by(User.name.asc()).all()


def _visible_reports():
    if current_user.role == "citizen":
        return FoodReport.query.filter_by(created_by_id=current_user.id).order_by(FoodReport.created_at.desc()).all()
    if current_user.role == "ngo":
        return (
            FoodReport.query.filter(
                (FoodReport.assigned_ngo_id == current_user.id)
                | (FoodReport.assigned_ngo_id.is_(None))
            )
            .order_by(FoodReport.created_at.desc())
            .all()
        )
    return FoodReport.query.order_by(FoodReport.created_at.desc()).all()


@food_bp.route("/", methods=["GET", "POST"])
@login_required
@roles_required("admin", "supervisor", "citizen", "ngo")
def index():
    form = FoodReportForm()
    can_report = current_user.role in {"admin", "supervisor", "citizen"}

    if can_report and form.validate_on_submit():
        ngos = _available_ngos()
        report = FoodReport(
            quantity=form.quantity.data.strip(),
            location=form.location.data.strip(),
            status="NGO Notified" if ngos else "Reported",
            created_by_id=current_user.id,
        )
        db.session.add(report)
        db.session.commit()
        flash("Food availability report created successfully.", "success")
        return redirect(url_for("food.index"))

    reports = _visible_reports()
    ngos = _available_ngos()
    return render_template("food.html", form=form, reports=reports, can_report=can_report, ngos=ngos)


@food_bp.route("/<int:report_id>/assign", methods=["POST"])
@login_required
@roles_required("admin", "supervisor")
def assign_ngo(report_id):
    report = FoodReport.query.get_or_404(report_id)
    form = FoodAssignForm()
    form.ngo_id.choices = [(ngo.id, ngo.name) for ngo in _available_ngos()]

    if form.validate_on_submit():
        report.assigned_ngo_id = form.ngo_id.data
        report.status = "NGO Notified"
        db.session.commit()
        flash("Food request assigned to NGO.", "success")
    else:
        flash("Unable to assign NGO for this food request.", "danger")
    return redirect(url_for("food.index"))


@food_bp.route("/<int:report_id>/accept", methods=["POST"])
@login_required
@roles_required("ngo")
def accept(report_id):
    report = FoodReport.query.get_or_404(report_id)
    if report.assigned_ngo_id and report.assigned_ngo_id != current_user.id:
        flash("This food request is already assigned to another NGO.", "danger")
        return redirect(url_for("food.index"))

    report.assigned_ngo_id = current_user.id
    report.status = "Accepted"
    db.session.commit()
    flash("Food request accepted successfully.", "success")
    return redirect(url_for("food.index"))


@food_bp.route("/<int:report_id>/status", methods=["POST"])
@login_required
@roles_required("admin", "supervisor", "ngo")
def update_status(report_id):
    report = FoodReport.query.get_or_404(report_id)
    if current_user.role == "ngo" and report.assigned_ngo_id != current_user.id:
        flash("You can only update food requests accepted by your NGO.", "danger")
        return redirect(url_for("food.index"))

    form = FoodStatusForm()
    if current_user.role == "ngo":
        form.status.choices = [(status, status) for status in ["Accepted", "Collected"]]
    else:
        form.status.choices = [(status, status) for status in ["Reported", "NGO Notified", "Accepted", "Collected"]]

    if form.validate_on_submit():
        report.status = form.status.data
        db.session.commit()
        flash("Food report status updated.", "success")
    else:
        flash("Unable to update food report status.", "danger")
    return redirect(url_for("food.index"))


@food_bp.route("/<int:report_id>/delete", methods=["POST"])
@login_required
@roles_required("admin")
def delete_report(report_id):
    report = FoodReport.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    flash("Food report deleted successfully.", "success")
    return redirect(url_for("food.index"))
