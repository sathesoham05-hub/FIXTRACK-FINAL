
from flask import Blueprint, render_template, request
from database import get_connection
from datetime import datetime, timedelta

intelligence_bp = Blueprint("intelligence", __name__)


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def analyze_machine(machine, records, today):
    total = len(records)
    recent_90 = 0
    recent_30 = 0
    valid_dates = []

    for record in records:
        date = parse_date(record["maintenance_date"])

        if date is None or date > today:
            continue

        valid_dates.append(date)
        days_ago = (today - date).days

        if days_ago <= 90:
            recent_90 += 1

        if days_ago <= 30:
            recent_30 += 1

    last_maintenance = max(valid_dates) if valid_dates else None

    if total == 0:
        return {
            "machine_number": machine["machine_number"],
            "machine_name": machine["machine_name"],
            "department": machine["department"],
            "score": None,
            "level": "Insufficient Data",
            "level_class": "unknown",
            "total": 0,
            "recent_90": 0,
            "recent_30": 0,
            "last_maintenance": None,
            "insight": "No maintenance history is available for this machine.",
            "machine_id": machine["id"]
        }

    # Explainable rule-based attention score.
    # This is NOT a failure probability.
    score = min(total * 6, 36)
    score += min(recent_90 * 12, 36)
    score += min(recent_30 * 7, 28)
    score = min(score, 100)

    if score >= 65:
        level = "High"
        level_class = "high"
    elif score >= 30:
        level = "Medium"
        level_class = "medium"
    else:
        level = "Low"
        level_class = "low"

    if recent_30 >= 3:
        insight = (
            f"{recent_30} maintenance activities were recorded "
            "in the last 30 days. Review repeated issues."
        )
    elif recent_90 >= 3:
        insight = (
            f"{recent_90} maintenance activities were recorded "
            "in the last 90 days. Consider an inspection."
        )
    elif total >= 5:
        insight = (
            f"This machine has {total} historical maintenance "
            "records. Review its service history."
        )
    else:
        insight = (
            "Limited maintenance activity is recorded. "
            "Continue routine monitoring."
        )

    return {
        "machine_number": machine["machine_number"],
        "machine_name": machine["machine_name"],
        "department": machine["department"],
        "score": score,
        "level": level,
        "level_class": level_class,
        "total": total,
        "recent_90": recent_90,
        "recent_30": recent_30,
        "last_maintenance": (
            last_maintenance.isoformat()
            if last_maintenance else None
        ),
        "insight": insight,
        "machine_id": machine["id"]
    }


@intelligence_bp.route("/intelligence")
def intelligence():
    connection = get_connection()

    machines = connection.execute(
        """
        SELECT id, machine_number, machine_name, department
        FROM machines
        ORDER BY machine_number
        """
    ).fetchall()

    maintenance = connection.execute(
        """
        SELECT machine_id, maintenance_date
        FROM maintenance
        """
    ).fetchall()

    connection.close()

    records_by_machine = {}

    for record in maintenance:
        records_by_machine.setdefault(
            record["machine_id"], []
        ).append(record)

    today = datetime.now().date()

    results = [
        analyze_machine(
            machine,
            records_by_machine.get(machine["id"], []),
            today
        )
        for machine in machines
    ]

    # Machines without data appear last.
    results.sort(
        key=lambda item: (
            item["score"] is None,
            -(item["score"] or 0),
            item["machine_number"]
        )
    )

    counts = {
        "high": sum(r["level_class"] == "high" for r in results),
        "medium": sum(r["level_class"] == "medium" for r in results),
        "low": sum(r["level_class"] == "low" for r in results),
        "unknown": sum(r["level_class"] == "unknown" for r in results)
    }

    selected_filter = request.args.get("level", "all").lower()

    if selected_filter not in [
        "all", "high", "medium", "low", "unknown"
    ]:
        selected_filter = "all"

    filtered_results = [
        r for r in results
        if selected_filter == "all"
        or r["level_class"] == selected_filter
    ]

    priority_machines = [
        r for r in results if r["level_class"] == "high"
    ][:3]

    return render_template(
        "intelligence/index.html",
        machines=filtered_results,
        counts=counts,
        total_machines=len(results),
        selected_filter=selected_filter,
        priority_machines=priority_machines,
        analyzed_on=today.strftime("%d %b %Y")
    )
