
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session
)
from werkzeug.security import check_password_hash
from database import get_connection


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        connection = get_connection()

        try:
            user = connection.execute(
                """
                SELECT id, username, password, role
                FROM users
                WHERE username = ?
                """,
                (username,)
            ).fetchone()

        finally:
            connection.close()

        if user and check_password_hash(
            user["password"], password
        ):
            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]

            return redirect(
                url_for("dashboard.dashboard")
            )

        return render_template(
            "auth/login.html",
            error="Invalid username or password."
        )

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
