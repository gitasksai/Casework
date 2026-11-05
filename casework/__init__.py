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

    app.config.setdefault("CASEWORK_USERNAME", os.environ.get("CASEWORK_USERNAME"))
    app.config.setdefault("CASEWORK_PASSWORD", os.environ.get("CASEWORK_PASSWORD"))
    app.config.setdefault("CASEWORK_API_TOKEN", os.environ.get("CASEWORK_API_TOKEN"))
    app.config.setdefault("MAX_CONTENT_LENGTH", 20 * 1024 * 1024)

    db.init_app(app)
    _install_basic_auth(app)

    from . import routes

    from . import imports

    app.register_blueprint(routes.bp)
    app.register_blueprint(imports.bp)
    routes.register_template_helpers(app)

    with app.app_context():
        db.create_all()

    return app


def _install_basic_auth(app):
    """Require a username/password for every page when CASEWORK_USERNAME and
    CASEWORK_PASSWORD are set. Off when they are not set (local single-user use)."""
    import hmac

    from flask import Response, request

    @app.before_request
    def _require_login():
        user, pwd = app.config.get("CASEWORK_USERNAME"), app.config.get("CASEWORK_PASSWORD")
        if not (user and pwd) or request.path.startswith("/api/"):
            return None  # /api/ uses CASEWORK_API_TOKEN instead (see imports.py)
        auth = request.authorization
        if (auth and auth.type == "basic"
                and hmac.compare_digest((auth.username or "").encode(), user.encode())
                and hmac.compare_digest((auth.password or "").encode(), pwd.encode())):
            return None
        return Response("Login required.", 401, {"WWW-Authenticate": 'Basic realm="Casework"'})
