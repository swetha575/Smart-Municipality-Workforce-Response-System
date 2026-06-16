from datetime import datetime, timedelta

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


TASK_STATUSES = ["Assigned", "In Progress", "Completed", "Reviewed", "Escalated"]
COMPLAINT_STATUSES = ["Submitted", "Assigned", "Task Created", "In Progress", "Resolved", "Escalated", "Rejected"]
FOOD_STATUSES = ["Reported", "NGO Notified", "Accepted", "Collected"]


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="citizen", index=True)
    face_embedding = db.Column(db.Text, nullable=True)
    managed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    manager = db.relationship("User", remote_side=[id], foreign_keys=[managed_by_id], backref=db.backref("managed_users", lazy=True))
    attendance_records = db.relationship("Attendance", backref="user", lazy=True, foreign_keys="Attendance.user_id", cascade="all, delete-orphan")
    attendance_overrides = db.relationship("Attendance", backref="marked_by", lazy=True, foreign_keys="Attendance.marked_by_id")
    created_tasks = db.relationship("Task", foreign_keys="Task.created_by_id", backref="creator", lazy=True)
    assigned_tasks = db.relationship("Task", foreign_keys="Task.assigned_to_id", backref="assignee", lazy=True)
    complaints = db.relationship("Complaint", backref="citizen", lazy=True, foreign_keys="Complaint.user_id", cascade="all, delete-orphan")
    assigned_complaints = db.relationship("Complaint", backref="assigned_supervisor", lazy=True, foreign_keys="Complaint.assigned_supervisor_id")
    reported_food = db.relationship("FoodReport", backref="reporter", lazy=True, foreign_keys="FoodReport.created_by_id")
    accepted_food = db.relationship("FoodReport", backref="assigned_ngo", lazy=True, foreign_keys="FoodReport.assigned_ngo_id")

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    @property
    def managed_workers(self):
        return [user for user in self.managed_users if user.role == "worker"]


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    marked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    location = db.Column(db.String(255), nullable=False)
    embedding = db.Column(db.Text, nullable=False)
    is_override = db.Column(db.Boolean, nullable=False, default=False)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaint.id"), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="Assigned", index=True)
    deadline = db.Column(db.Date, nullable=False)
    before_image = db.Column(db.String(255), nullable=True)
    after_image = db.Column(db.String(255), nullable=True)
    escalated = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    complaint = db.relationship("Complaint", backref=db.backref("linked_task", uselist=False), foreign_keys=[complaint_id])


class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    assigned_supervisor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    description = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(255), nullable=True)
    voice = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="Submitted", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class FoodReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="Reported", index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assigned_ngo_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def _ensure_columns(table_name, columns):
    inspector = inspect(db.engine)
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    with db.engine.begin() as connection:
        for column_name, definition in columns.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


def run_schema_migrations():
    _ensure_columns(
        "user",
        {
            "managed_by_id": "INTEGER",
        },
    )
    _ensure_columns(
        "attendance",
        {
            "marked_by_id": "INTEGER",
            "is_override": "BOOLEAN NOT NULL DEFAULT 0",
        },
    )
    _ensure_columns(
        "task",
        {
            "location": "VARCHAR(255) NOT NULL DEFAULT 'Unspecified municipal area'",
            "complaint_id": "INTEGER",
            "before_image": "VARCHAR(255)",
            "after_image": "VARCHAR(255)",
            "escalated": "BOOLEAN NOT NULL DEFAULT 0",
        },
    )
    _ensure_columns(
        "complaint",
        {
            "assigned_supervisor_id": "INTEGER",
        },
    )
    _ensure_columns(
        "food_report",
        {
            "assigned_ngo_id": "INTEGER",
        },
    )


def _first_user_by_role(role):
    return User.query.filter_by(role=role).order_by(User.id.asc()).first()


def _backfill_hierarchy():
    admin = _first_user_by_role("admin")
    supervisor = _first_user_by_role("supervisor")

    if admin:
        for managed_role in ("supervisor", "ngo"):
            for user in User.query.filter_by(role=managed_role).all():
                if user.managed_by_id is None:
                    user.managed_by_id = admin.id

    if supervisor:
        for worker in User.query.filter_by(role="worker").all():
            if worker.managed_by_id is None:
                worker.managed_by_id = supervisor.id

    if supervisor:
        for complaint in Complaint.query.filter(Complaint.assigned_supervisor_id.is_(None)).all():
            complaint.assigned_supervisor_id = supervisor.id
            if complaint.status in {"Submitted", "Under Review"}:
                complaint.status = "Assigned"

    for task in Task.query.all():
        if not task.location:
            task.location = task.complaint.location if task.complaint else "Unspecified municipal area"
        if task.status == "Pending":
            task.status = "Assigned"

    for food_report in FoodReport.query.all():
        if food_report.status == "Pending NGO Action":
            food_report.status = "Reported"
        elif food_report.status == "NGO Notified":
            food_report.status = "NGO Notified"

    db.session.commit()


def seed_initial_data(app):
    if User.query.count() == 0:
        admin = User(name="System Administrator", email=app.config["DEFAULT_ADMIN_EMAIL"], role="admin")
        admin.set_password(app.config["DEFAULT_ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.flush()

        supervisor = User(name="Ward Supervisor", email="supervisor@example.com", role="supervisor", managed_by_id=admin.id)
        supervisor.set_password("Supervisor@123")
        db.session.add(supervisor)
        db.session.flush()

        worker = User(name="Field Worker", email="worker@example.com", role="worker", managed_by_id=supervisor.id)
        worker.set_password("Worker@123")

        citizen = User(name="Citizen User", email="citizen@example.com", role="citizen")
        citizen.set_password("Citizen@123")

        ngo = User(name="NGO Partner", email="ngo@example.com", role="ngo", managed_by_id=admin.id)
        ngo.set_password("Ngo@12345")

        db.session.add_all([worker, citizen, ngo])
        db.session.flush()

        sample_complaint = Complaint(
            user_id=citizen.id,
            assigned_supervisor_id=supervisor.id,
            description="Street light near park entrance is not functioning.",
            location="Ward 11, Park Road",
            status="Task Created",
        )
        db.session.add(sample_complaint)
        db.session.flush()

        sample_task = Task(
            title="Inspect drainage blockage",
            description="Visit sector 12 and coordinate clearing of the reported drain blockage.",
            location="Sector 12",
            assigned_to_id=worker.id,
            created_by_id=supervisor.id,
            complaint_id=sample_complaint.id,
            status="In Progress",
            deadline=(datetime.utcnow() + timedelta(days=2)).date(),
        )
        sample_food = FoodReport(
            quantity="120 meal packs",
            location="Community Hall, Sector 8",
            status="NGO Notified",
            created_by_id=citizen.id,
            assigned_ngo_id=ngo.id,
        )
        db.session.add_all([sample_task, sample_food])
        db.session.commit()

    _backfill_hierarchy()


def prepare_database(app):
    db.create_all()
    run_schema_migrations()
    seed_initial_data(app)
