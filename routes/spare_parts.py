
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


spare_parts_bp = Blueprint(
    "spare_parts",
    __name__,
    url_prefix="/spare-parts"
)


def require_admin():
    if session.get("role") != "admin":
        abort(403)


@spare_parts_bp.route("/")
def spare_parts():

    current_filter = request.args.get("filter", "all")

    connection = get_connection()

    try:

        if current_filter == "low_stock":

            parts = connection.execute("""
                SELECT *
                FROM spare_parts
                WHERE current_stock <= reorder_level
                ORDER BY id DESC
            """).fetchall()

        elif current_filter == "in_stock":

            parts = connection.execute("""
                SELECT *
                FROM spare_parts
                WHERE current_stock > reorder_level
                ORDER BY id DESC
            """).fetchall()

        else:

            current_filter = "all"

            parts = connection.execute("""
                SELECT *
                FROM spare_parts
                ORDER BY id DESC
            """).fetchall()

    finally:
        connection.close()

    return render_template(
        "spare_parts/index.html",
        spare_parts=parts,
        current_filter=current_filter
    )


@spare_parts_bp.route(
    "/add",
    methods=["GET", "POST"]
)
def add_spare_part():

    require_admin()

    if request.method == "POST":

        part_code = request.form["part_code"]
        part_name = request.form["part_name"]
        category = request.form["category"]
        brand = request.form["brand"]
        specification = request.form["specification"]
        current_stock = request.form["current_stock"]
        reorder_level = request.form["reorder_level"]
        location = request.form["location"]

        connection = get_connection()

        try:
            connection.execute(
                """
                INSERT INTO spare_parts (
                    part_code,
                    part_name,
                    category,
                    brand,
                    specification,
                    current_stock,
                    reorder_level,
                    location
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    part_code,
                    part_name,
                    category,
                    brand,
                    specification,
                    current_stock,
                    reorder_level,
                    location
                )
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

        return redirect(
            url_for("spare_parts.spare_parts")
        )

    return render_template("spare_parts/add.html")


@spare_parts_bp.route(
    "/edit/<int:part_id>",
    methods=["GET", "POST"]
)
def edit_spare_part(part_id):

    require_admin()

    connection = get_connection()

    try:
        part = connection.execute(
            "SELECT * FROM spare_parts WHERE id = ?",
            (part_id,)
        ).fetchone()

        if part is None:
            abort(404)

        if request.method == "POST":

            part_code = request.form["part_code"]
            part_name = request.form["part_name"]
            category = request.form["category"]
            brand = request.form["brand"]
            specification = request.form["specification"]
            current_stock = request.form["current_stock"]
            reorder_level = request.form["reorder_level"]
            location = request.form["location"]

            connection.execute(
                """
                UPDATE spare_parts
                SET part_code = ?,
                    part_name = ?,
                    category = ?,
                    brand = ?,
                    specification = ?,
                    current_stock = ?,
                    reorder_level = ?,
                    location = ?
                WHERE id = ?
                """,
                (
                    part_code,
                    part_name,
                    category,
                    brand,
                    specification,
                    current_stock,
                    reorder_level,
                    location,
                    part_id
                )
            )

            connection.commit()

            return redirect(
                url_for("spare_parts.spare_parts")
            )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return render_template(
        "spare_parts/edit.html",
        part=part
    )


@spare_parts_bp.route(
    "/delete/<int:part_id>",
    methods=["POST"]
)
def delete_spare_part(part_id):

    require_admin()

    connection = get_connection()

    try:
        connection.execute(
            "DELETE FROM spare_parts WHERE id = ?",
            (part_id,)
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return redirect(
        url_for("spare_parts.spare_parts")
    )
