from pathlib import Path

from flask import Flask
from flask_login import LoginManager
from flask_wtf import CSRFProtect

from config import Config


login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"
csrf = CSRFProtect()


MODULE_ACCESS = {
    "attendance": {"admin", "supervisor", "worker"},
    "tasks": {"admin", "supervisor", "worker"},
    "complaints": {"admin", "supervisor", "citizen"},
    "food": {"admin", "supervisor", "citizen", "ngo"},
    "analytics": {"admin"},
    "users": {"admin"},
}


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    from .models import db, prepare_database

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    upload_folder = Path(app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)

    from .routes.admin import admin_bp
    from .routes.attendance import attendance_bp
    from .routes.auth import auth_bp
    from .routes.complaints import complaints_bp
    from .routes.food import food_bp
    from .routes.tasks import tasks_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(attendance_bp, url_prefix="/attendance")
    app.register_blueprint(tasks_bp, url_prefix="/tasks")
    app.register_blueprint(complaints_bp, url_prefix="/complaints")
    app.register_blueprint(food_bp, url_prefix="/food")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.context_processor
    def inject_ui_context():
        return {
            "role_labels": {
                "admin": "Administrator",
                "supervisor": "Supervisor",
                "worker": "Worker",
                "citizen": "Citizen",
                "ngo": "NGO Partner",
            },
            "module_access": MODULE_ACCESS,
        }

    with app.app_context():
        prepare_database(app)

    return app


@login_manager.user_loader
def load_user(user_id):
    from .models import User, db

    return db.session.get(User, int(user_id))
