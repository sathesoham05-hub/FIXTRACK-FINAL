
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    abort
)

from database import get_connection


machines_bp = Blueprint(
    "machines",
    __name__,
    url_prefix="/machines"
)


def require_admin():
    if session.get("role") != "admin":
        abort(403)


@machines_bp.route("/")
def machines():

    connection = get_connection()

    try:
        machines = connection.execute(
            "SELECT * FROM machines ORDER BY id DESC"
        ).fetchall()

    finally:
        connection.close()

    return render_template(
        "machines/index.html",
        machines=machines
    )


@machines_bp.route("/add", methods=["GET", "POST"])
def add_machine():

    require_admin()

    if request.method == "POST":

        machine_number = request.form["machine_number"]
        machine_name = request.form["machine_name"]
        department = request.form["department"]
        manufacturer = request.form["manufacturer"]
        model = request.form["model"]
        status = request.form["status"]

        connection = get_connection()

        try:
            connection.execute(
                """
                INSERT INTO machines (
                    machine_number,
                    machine_name,
                    department,
                    manufacturer,
                    model,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    machine_number,
                    machine_name,
                    department,
                    manufacturer,
                    model,
                    status
                )
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

        return redirect(url_for("machines.machines"))

    return render_template("machines/add.html")


@machines_bp.route(
    "/edit/<int:machine_id>",
    methods=["GET", "POST"]
)
def edit_machine(machine_id):

    require_admin()

    connection = get_connection()

    try:
        machine = connection.execute(
            "SELECT * FROM machines WHERE id = ?",
            (machine_id,)
        ).fetchone()

        if machine is None:
            abort(404)

        if request.method == "POST":

            machine_number = request.form["machine_number"]
            machine_name = request.form["machine_name"]
            department = request.form["department"]
            manufacturer = request.form["manufacturer"]
            model = request.form["model"]
            status = request.form["status"]

            connection.execute(
                """
                UPDATE machines
                SET machine_number = ?,
                    machine_name = ?,
                    department = ?,
                    manufacturer = ?,
                    model = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    machine_number,
                    machine_name,
                    department,
                    manufacturer,
                    model,
                    status,
                    machine_id
                )
            )

            connection.commit()

            return redirect(
                url_for("machines.machines")
            )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return render_template(
        "machines/edit.html",
        machine=machine
    )


@machines_bp.route(
    "/delete/<int:machine_id>",
    methods=["POST"]
)
def delete_machine(machine_id):

    require_admin()

    connection = get_connection()

    try:
        connection.execute(
            "DELETE FROM machines WHERE id = ?",
            (machine_id,)
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return redirect(url_for("machines.machines"))
