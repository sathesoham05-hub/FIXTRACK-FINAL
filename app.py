
import os
import secrets
from pathlib import Path

from flask import (
    Flask,
    session,
    redirect,
    url_for,
    request,
    abort
)

from database import create_tables, get_connection

from routes.dashboard import dashboard_bp
from routes.machines import machines_bp
from routes.spare_parts import spare_parts_bp
from routes.maintenance import maintenance_bp
from routes.auth import auth_bp
from routes.reports import reports_bp
from routes.intelligence import intelligence_bp
from routes.copilot import copilot_bp


app = Flask(__name__)

# ---------------------------------------------
# SECURITY CONFIGURATION
# ---------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
SECRET_FILE = BASE_DIR / ".fixtrack-secret"

secret_key = os.environ.get("FIXTRACK_SECRET_KEY")

if not secret_key:
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(
            secrets.token_hex(32),
            encoding="utf-8"
        )

    secret_key = SECRET_FILE.read_text(
        encoding="utf-8"
    ).strip()

app.secret_key = secret_key

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("FIXTRACK_HTTPS") == "1"
    )
)


# ---------------------------------------------
# REGISTER BLUEPRINTS
# ---------------------------------------------

app.register_blueprint(dashboard_bp)
app.register_blueprint(machines_bp)
app.register_blueprint(spare_parts_bp)
app.register_blueprint(maintenance_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(intelligence_bp)
app.register_blueprint(copilot_bp)


# ---------------------------------------------
# USER PERMISSIONS
# ---------------------------------------------

# Only these specific pages are available
# to regular users.

USER_ALLOWED_GET_ENDPOINTS = {
    "dashboard.dashboard",
    "dashboard.analytics",
    "dashboard.machine_analytics",

    "machines.machines",
    "spare_parts.spare_parts",
    "maintenance.maintenance",
    "reports.reports",
    "intelligence.intelligence",
    "copilot.copilot",
}

# This Copilot endpoint retrieves information
# but does not modify the database.

USER_ALLOWED_POST_ENDPOINTS = {
    "copilot.ask_copilot",
}


# ---------------------------------------------
# AUTHENTICATION AND AUTHORIZATION
# ---------------------------------------------

@app.before_request
def require_login():

    endpoint = request.endpoint

    if endpoint in ("auth.login", "static"):
        return None

    if endpoint is None:
        return None

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("auth.login"))

    connection = get_connection()

    try:
        user = connection.execute(
            """
            SELECT id, username, role
            FROM users
            WHERE id = ?
            """,
            (user_id,)
        ).fetchone()

    finally:
        connection.close()

    if user is None:
        session.clear()
        return redirect(url_for("auth.login"))

    role = user["role"]

    if role not in ("admin", "user"):
        session.clear()
        abort(403)

    session["username"] = user["username"]
    session["role"] = role

    # Both roles may log out.
    if endpoint == "auth.logout":
        return None

    # Admin: full application access.
    if role == "admin":
        return None

    # User: verified read-only pages.
    if (
        request.method in ("GET", "HEAD")
        and endpoint in USER_ALLOWED_GET_ENDPOINTS
    ):
        return None

    # User: operational Copilot questions.
    if (
        request.method == "POST"
        and endpoint in USER_ALLOWED_POST_ENDPOINTS
    ):
        return None

    # Block every other operation.
    abort(403)


# ---------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------

create_tables()


if __name__ == "__main__":
    app.run(debug=True)
