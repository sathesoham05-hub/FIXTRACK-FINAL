
import re

from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    session,
    abort
)

from database import get_connection


copilot_bp = Blueprint("copilot", __name__)


SUGGESTIONS = [
    "Give me a factory overview",
    "Which spare parts are low on stock?",
    "Which machines have the most maintenance?",
    "What are the most consumed spare parts?",
    "Which machines need attention?",
    "Show the latest maintenance activity",
    "Show maintenance history for FLEXO-001",
    "Check stock for SP-001"
]


# -------------------------------------------------
# ACCESS CONTROL
# -------------------------------------------------

COPILOT_ALLOWED_ROLES = {"admin", "user"}


def check_copilot_access():
    if session.get("role") not in COPILOT_ALLOWED_ROLES:
        abort(403)


# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def make_answer(title, message, rows=None):
    return {
        "title": title,
        "message": message,
        "rows": rows or []
    }


def has_any(text, phrases):
    """
    Check whether a question contains any supported phrase.
    Handles uppercase text, punctuation, hyphens
    and extra spaces.
    """

    normalized_text = re.sub(
        r"[^a-zA-Z0-9]+",
        " ",
        str(text).lower()
    ).strip()

    for phrase in phrases:

        normalized_phrase = re.sub(
            r"[^a-zA-Z0-9]+",
            " ",
            str(phrase).lower()
        ).strip()

        if not normalized_phrase:
            continue

        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(normalized_phrase).replace(r"\ ", r"\s+")
            + r"(?![a-z0-9])"
        )

        if re.search(pattern, normalized_text):
            return True

    return False


def find_identifier(question, records, field):
    candidates = sorted(
        [
            record for record in records
            if record[field] and str(record[field]).strip()
        ],
        key=lambda record: len(str(record[field])),
        reverse=True
    )

    for record in candidates:
        identifier = str(record[field]).strip()

        pattern = (
            r"(?<![A-Za-z0-9])"
            + re.escape(identifier)
            + r"(?![A-Za-z0-9])"
        )

        if re.search(pattern, question, re.IGNORECASE):
            return record

    return None

def find_requested_code(question, prefix):

    pattern = (
        r"\b" + prefix +
        r"\s+(?:number\s+|code\s+|id\s+)?"
        r"([A-Za-z0-9][A-Za-z0-9_-]*)"
        r"(?=\s|$|[?.!,])"
    )

    match = re.search(
        pattern,
        str(question),
        re.IGNORECASE
    )

    return match.group(1) if match else None

# -------------------------------------------------
# MACHINE LOOKUP
# -------------------------------------------------

def machine_lookup(connection, machine, question):
    machine_id = machine["id"]
    number = machine["machine_number"]

    total = connection.execute(
        """
        SELECT COUNT(*)
        FROM maintenance
        WHERE machine_id = ?
        """,
        (machine_id,)
    ).fetchone()[0]

    latest = connection.execute(
        """
        SELECT maintenance_date, remarks
        FROM maintenance
        WHERE machine_id = ?
        ORDER BY maintenance_date DESC, id DESC
        LIMIT 5
        """,
        (machine_id,)
    ).fetchall()

    if has_any(question, [
        "history", "maintenance", "repairs",
        "repaired", "serviced", "service"
    ]):
        rows = [
            f"Total maintenance records: {total}"
        ]

        for record in latest:
            date = record["maintenance_date"] or "Unknown date"
            remarks = str(record["remarks"] or "").strip()

            description = str(date)

            if remarks:
                description += f" — {remarks[:150]}"

            rows.append(description)

        if not latest:
            rows.append("No maintenance records available.")

        return make_answer(
            f"Maintenance History — {number}",
            f"Found {total} maintenance records for {number}. "
            "Showing up to five latest activities:",
            rows
        )

    return make_answer(
        f"Machine Details — {number}",
        "Here is the information stored for this machine:",
        [
            f"Machine number: {number}",
            f"Machine name: {machine['machine_name'] or 'Not specified'}",
            f"Department: {machine['department'] or 'Not specified'}",
            f"Manufacturer: {machine['manufacturer'] or 'Not specified'}",
            f"Model: {machine['model'] or 'Not specified'}",
            f"Status: {machine['status'] or 'Not specified'}",
            f"Maintenance records: {total}"
        ]
    )


# -------------------------------------------------
# SPARE PART LOOKUP
# -------------------------------------------------

def part_lookup(connection, part, question):
    code = part["part_code"]
    name = part["part_name"]

    stock = part["current_stock"] or 0
    reorder = part["reorder_level"] or 0

    if stock <= 0:
        stock_status = "Out of stock"
    elif stock <= reorder:
        stock_status = "Low stock"
    else:
        stock_status = "Stock available"

    consumption = connection.execute(
        """
        SELECT COALESCE(SUM(quantity), 0)
        FROM maintenance
        WHERE spare_part_id = ?
          AND quantity > 0
        """,
        (part["id"],)
    ).fetchone()[0]

    if has_any(question, [
        "stock", "available", "availability",
        "quantity", "inventory", "reorder"
    ]):
        return make_answer(
            f"Stock Check — {code}",
            f"Current inventory status for {name}:",
            [
                f"Part code: {code}",
                f"Part name: {name}",
                f"Current stock: {stock}",
                f"Reorder level: {reorder}",
                f"Status: {stock_status}",
                f"Recorded maintenance consumption: {consumption}"
            ]
        )

    return make_answer(
        f"Spare Part Details — {code}",
        "Here are the stored details for this spare part:",
        [
            f"Part code: {code}",
            f"Part name: {name}",
            f"Category: {part['category'] or 'Not specified'}",
            f"Brand: {part['brand'] or 'Not specified'}",
            f"Specification: {part['specification'] or 'Not specified'}",
            f"Location: {part['location'] or 'Not specified'}",
            f"Current stock: {stock}",
            f"Reorder level: {reorder}",
            f"Stock status: {stock_status}",
            f"Recorded maintenance consumption: {consumption}"
        ]
    )


# -------------------------------------------------
# COPILOT ANSWER ENGINE
# -------------------------------------------------

def answer_question(question):

    q = " ".join(str(question).lower().split())

    connection = get_connection()

    try:

        machines = connection.execute(
            """
            SELECT id, machine_number, machine_name,
                   department, manufacturer, model, status
            FROM machines
            """
        ).fetchall()

        parts = connection.execute(
            """
            SELECT id, part_code, part_name, category,
                   brand, specification, current_stock,
                   reorder_level, location
            FROM spare_parts
            """
        ).fetchall()

        # IDENTIFY EXISTING RECORDS

        machine = find_identifier(
            question, machines, "machine_number"
        )

        part = find_identifier(
            question, parts, "part_code"
        )

        part_terms = [
            "part", "spare", "stock", "inventory",
            "availability", "reorder", "quantity",
            "consumption", "used"
        ]

        if machine and part:

            if has_any(q, part_terms):
                return part_lookup(connection, part, q)

            return machine_lookup(connection, machine, q)

        if machine:
            return machine_lookup(connection, machine, q)

        if part:
            return part_lookup(connection, part, q)

        # CHECK REQUESTED MACHINE/PART CODES

        requested_machine = find_requested_code(
            question, "machine"
        )

        requested_part = find_requested_code(
            question, r"(?:spare\s+part|part)"
        )

        ignored_machine_words = {
            "details", "history", "status", "number",
            "health", "attention", "with", "has",
            "maintenance", "records", "is", "needs",
            "need", "the", "a", "which", "all",
            "any", "for", "show", "list"
        }

        ignored_part_words = {
            "details", "stock", "code", "number",
            "usage", "consumption", "inventory",
            "is", "has", "with", "the", "a",
            "which", "all", "any", "for",
            "show", "list", "low", "running",
            "below", "minimum", "needs", "need"
        }

        if (
            requested_machine
            and requested_machine.lower() not in ignored_machine_words
        ):
            return make_answer(
                "Machine Not Found",
                f"I couldn't find machine {requested_machine} "
                "in the FixTrack database. Please check its number."
            )

        if (
            requested_part
            and requested_part.lower() not in ignored_part_words
        ):
            return make_answer(
                "Spare Part Not Found",
                f"I couldn't find spare part {requested_part} "
                "in the FixTrack database. Please check its code."
            )

        # LOW STOCK

        if has_any(q, [
            "low stock",
            "low on stock",
            "low in stock",
            "running low",
            "running out",
            "shortage",
            "shortages",
            "stock shortage",
            "stock shortages",
            "low inventory",
            "insufficient stock",
            "out of stock",
            "reorder",
            "restock",
            "restocking",
            "replenish",
            "below reorder level",
            "below the reorder level",
            "below minimum stock",
            "minimum stock",
            "need ordering",
            "needs ordering",
            "parts to order"
        ]):

            records = connection.execute(
                """
                SELECT part_code, part_name,
                       current_stock, reorder_level
                FROM spare_parts
                WHERE current_stock <= reorder_level
                ORDER BY current_stock ASC, part_name
                LIMIT 10
                """
            ).fetchall()

            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM spare_parts
                WHERE current_stock <= reorder_level
                """
            ).fetchone()[0]

            rows = [
                (
                    f"{r['part_code']} — {r['part_name']}: "
                    f"Stock {r['current_stock']} "
                    f"(Reorder level: {r['reorder_level']})"
                )
                for r in records
            ]

            return make_answer(
                "Low Stock Analysis",
                f"{count} spare parts are at or below their "
                "reorder level. Showing up to 10 items:",
                rows or ["No low-stock items found."]
            )

        # MACHINE ATTENTION

        if has_any(q, [
            "attention",
            "risk",
            "health",
            "critical",
            "priority",
            "problem machines",
            "machines with problems",
            "machines with issues",
            "machines needing attention",
            "machine problems",
            "machine issues",
            "maintenance intensive"
        ]):

            records = connection.execute(
                """
                SELECT m.machine_number,
                       COUNT(mt.id) AS total
                FROM machines m
                JOIN maintenance mt ON mt.machine_id = m.id
                GROUP BY m.id
                ORDER BY total DESC, m.machine_number
                LIMIT 5
                """
            ).fetchall()

            return make_answer(
                "Machine Attention Review",
                "These machines have the highest number of "
                "recorded maintenance activities. This is a "
                "historical ranking, not a failure prediction:",
                [
                    f"{r['machine_number']}: {r['total']} records"
                    for r in records
                ] or ["No maintenance history available."]
            )

        # SPARE PARTS CONSUMPTION

        if has_any(q, [
            "consumed",
            "consumption",
            "most used",
            "used the most",
            "parts usage",
            "spare usage",
            "highest consumption",
            "most consumed",
            "parts consumed",
            "usage statistics"
        ]):

            records = connection.execute(
                """
                SELECT sp.part_code, sp.part_name,
                       SUM(mt.quantity) AS used
                FROM maintenance mt
                JOIN spare_parts sp ON sp.id = mt.spare_part_id
                WHERE mt.quantity > 0
                GROUP BY sp.id
                ORDER BY used DESC
                LIMIT 5
                """
            ).fetchall()

            return make_answer(
                "Spare Parts Consumption",
                "These are the five most consumed spare parts "
                "recorded in FixTrack:",
                [
                    f"{r['part_code']} — {r['part_name']}: "
                    f"{r['used']} used"
                    for r in records
                ] or ["No spare parts consumption recorded."]
            )

        # MOST MAINTAINED MACHINES

        if has_any(q, [
            "most maintenance",
            "most repairs",
            "frequent maintenance",
            "frequent repairs",
            "most serviced",
            "most maintained",
            "highest maintenance",
            "highest number of repairs",
            "maintenance frequency",
            "maintenance count"
        ]):

            records = connection.execute(
                """
                SELECT m.machine_number,
                       COUNT(mt.id) AS total
                FROM machines m
                JOIN maintenance mt ON mt.machine_id = m.id
                GROUP BY m.id
                ORDER BY total DESC
                LIMIT 5
                """
            ).fetchall()

            return make_answer(
                "Maintenance Frequency",
                "Machines with the highest recorded "
                "maintenance frequency:",
                [
                    f"{r['machine_number']}: {r['total']} records"
                    for r in records
                ] or ["No maintenance records found."]
            )

        # LATEST MAINTENANCE

        if has_any(q, [
            "latest",
            "recent",
            "last maintenance",
            "maintenance history",
            "recent maintenance",
            "recent repairs",
            "last repairs",
            "latest repairs",
            "maintenance records",
            "recent records"
        ]):

            records = connection.execute(
                """
                SELECT m.machine_number,
                       mt.maintenance_date, mt.remarks
                FROM maintenance mt
                JOIN machines m ON m.id = mt.machine_id
                ORDER BY mt.maintenance_date DESC, mt.id DESC
                LIMIT 5
                """
            ).fetchall()

            return make_answer(
                "Recent Maintenance",
                "Here are the five latest recorded "
                "maintenance activities:",
                [
                    (
                        f"{r['machine_number']} — "
                        f"{r['maintenance_date'] or 'Unknown date'}"
                        + (
                            f" — {str(r['remarks'])[:120]}"
                            if r["remarks"] else ""
                        )
                    )
                    for r in records
                ] or ["No maintenance records found."]
            )

        # FACTORY OVERVIEW

        if has_any(q, [
            "overview",
            "summary",
            "total",
            "how many",
            "factory status",
            "statistics",
            "factory summary",
            "factory statistics",
            "overall status",
            "factory overview"
        ]):

            machine_count = connection.execute(
                "SELECT COUNT(*) FROM machines"
            ).fetchone()[0]

            part_count = connection.execute(
                "SELECT COUNT(*) FROM spare_parts"
            ).fetchone()[0]

            maintenance_count = connection.execute(
                "SELECT COUNT(*) FROM maintenance"
            ).fetchone()[0]

            low_stock_count = connection.execute(
                """
                SELECT COUNT(*) FROM spare_parts
                WHERE current_stock <= reorder_level
                """
            ).fetchone()[0]

            return make_answer(
                "Factory Overview",
                "Here is the current overview of your "
                "FixTrack database:",
                [
                    f"Registered machines: {machine_count}",
                    f"Spare parts: {part_count}",
                    f"Maintenance records: {maintenance_count}",
                    f"Low-stock items: {low_stock_count}"
                ]
            )

        # DEFAULT RESPONSE

        return make_answer(
            "Try another question",
            "I can answer questions about factory statistics, "
            "specific machine numbers, spare part codes, "
            "inventory, machine maintenance and spare parts "
            "consumption. Try rephrasing your question.",
            SUGGESTIONS
        )

    finally:
        connection.close()
# -------------------------------------------------
# COPILOT ROUTES
# -------------------------------------------------

@copilot_bp.route("/copilot")
def copilot():
    check_copilot_access()

    return render_template(
        "copilot/index.html",
        suggestions=SUGGESTIONS
    )


@copilot_bp.route("/copilot/ask", methods=["POST"])
def ask_copilot():
    check_copilot_access()

    data = request.get_json(silent=True) or {}
    question = data.get("question", "")

    if not isinstance(question, str):
        return jsonify({
            "error": "Invalid question."
        }), 400

    question = question.strip()

    if not question or len(question) > 300:
        return jsonify({
            "error": "Enter a question of up to 300 characters."
        }), 400

    try:
        return jsonify(answer_question(question))

    except Exception:
        return jsonify({
            "error": "Unable to retrieve database information."
        }), 500
