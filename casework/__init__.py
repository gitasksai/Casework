import os

from flask import Flask

from .models import db


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CASEWORK_SECRET_KEY", "dev-change-me"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "CASEWORK_DATABASE_URL",
            "sqlite:///" + os.path.join(app.instance_path, "casework.db"),
        ),
        SWARM_AGE_DAYS=int(os.environ.get("CASEWORK_SWARM_AGE_DAYS", 5)),
        STRUCTURED_INVESTIGATION_AGE_DAYS=int(os.environ.get("CASEWORK_SI_AGE_DAYS", 15)),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    from . import routes

    app.register_blueprint(routes.bp)
    routes.register_template_helpers(app)

    with app.app_context():
        db.create_all()

    return app
