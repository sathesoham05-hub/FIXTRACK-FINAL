from flask import Blueprint, render_template

from database import get_connection


dashboard_bp = Blueprint(
    "dashboard",
    __name__
)


# ==============================
# MAIN DASHBOARD
# ==============================

@dashboard_bp.route("/")
def dashboard():

    connection = get_connection()

    total_machines = connection.execute(
        "SELECT COUNT(*) FROM machines"
    ).fetchone()[0]

    total_spare_parts = connection.execute(
        "SELECT COUNT(*) FROM spare_parts"
    ).fetchone()[0]

    low_stock_items = connection.execute("""
        SELECT COUNT(*)
        FROM spare_parts
        WHERE current_stock <= reorder_level
    """).fetchone()[0]

    total_maintenance = connection.execute(
        "SELECT COUNT(*) FROM maintenance"
    ).fetchone()[0]

    # RECENT MAINTENANCE RECORDS
    # Original query restored

    recent_records = connection.execute("""
        SELECT
            maintenance.quantity,
            maintenance.maintenance_date,
            maintenance.remarks,

            machines.machine_number,
            machines.machine_name,

            spare_parts.part_name,
            spare_parts.brand,
            spare_parts.specification

        FROM maintenance

        JOIN machines
            ON maintenance.machine_id = machines.id

        LEFT JOIN spare_parts
            ON maintenance.spare_part_id = spare_parts.id

        ORDER BY maintenance.id DESC

        LIMIT 5
    """).fetchall()

    connection.close()

    return render_template(
        "dashboard/index.html",

        total_machines=total_machines,
        total_spare_parts=total_spare_parts,
        low_stock_items=low_stock_items,
        total_maintenance=total_maintenance,

        recent_records=recent_records
    )


# ==============================
# OVERALL ANALYTICS
# ==============================

@dashboard_bp.route('/analytics')
def analytics():

    from datetime import datetime, timedelta
    from flask import request

    conn = get_connection()
    cursor = conn.cursor()

    # GET DATE FILTER
    period = request.args.get('period', '12months')

    today = datetime.today().date()

    if period == '30days':
        start_date = today - timedelta(days=30)

    elif period == '3months':
        start_date = today - timedelta(days=90)

    elif period == '6months':
        start_date = today - timedelta(days=180)

    elif period == 'custom':
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date or not end_date:
            period = '12months'
            start_date = today.replace(day=1)
            start_date = start_date.replace(
                year=start_date.year - 1
            ) if start_date.month == 1 else start_date.replace(
                month=start_date.month - 1
            )

            end_date = today

    else:
        period = '12months'
        start_date = today - timedelta(days=365)
        end_date = today

    if period != 'custom':
        end_date = today

    # MACHINE COUNTS
    cursor.execute("SELECT COUNT(*) FROM machines")
    total_machines = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM machines
        WHERE status = 'Active'
    """)
    active_machines = cursor.fetchone()[0]

    # MACHINE-WISE ANALYTICS
    cursor.execute("""
        SELECT
            m.id,
            m.machine_number,
            m.machine_name,
            m.department,
            m.status,
            COUNT(mt.id) AS total_maintenance
        FROM machines AS m
        LEFT JOIN maintenance AS mt
            ON m.id = mt.machine_id
            AND date(mt.maintenance_date)
                BETWEEN date(?) AND date(?)
        GROUP BY
            m.id,
            m.machine_number,
            m.machine_name,
            m.department,
            m.status
        ORDER BY total_maintenance DESC
    """, (start_date, end_date))

    machine_rows = cursor.fetchall()

    machine_data = [
        {
            "id": row["id"],
            "machine_number": row["machine_number"],
            "machine_name": row["machine_name"],
            "department": row["department"],
            "status": row["status"],
            "total": row["total_maintenance"]
        }
        for row in machine_rows
    ]

    # MONTHLY ANALYTICS
    cursor.execute("""
        SELECT
            strftime('%Y-%m', maintenance_date) AS month,
            COUNT(*) AS total
        FROM maintenance
        WHERE date(maintenance_date)
            BETWEEN date(?) AND date(?)
        GROUP BY strftime('%Y-%m', maintenance_date)
        ORDER BY month
    """, (start_date, end_date))

    rows = cursor.fetchall()

    monthly_data = {
        row['month']: row['total']
        for row in rows
    }

    # TOTAL MAINTENANCE IN SELECTED PERIOD
    cursor.execute("""
        SELECT COUNT(*)
        FROM maintenance
        WHERE date(maintenance_date)
            BETWEEN date(?) AND date(?)
    """, (start_date, end_date))

    total_maintenance = cursor.fetchone()[0]

    # MACHINES WITHOUT MAINTENANCE IN SELECTED PERIOD
    cursor.execute("""
        SELECT COUNT(*)
        FROM machines AS m
        WHERE NOT EXISTS (
            SELECT 1
            FROM maintenance AS mt
            WHERE mt.machine_id = m.id
            AND date(mt.maintenance_date)
                BETWEEN date(?) AND date(?)
        )
    """, (start_date, end_date))

    machines_without_maintenance = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'analytics.html',
        monthly_data=monthly_data,
        machine_data=machine_data,
        total_machines=total_machines,
        active_machines=active_machines,
        total_maintenance=total_maintenance,
        machines_without_maintenance=machines_without_maintenance,
        period=period,
        start_date=start_date,
        end_date=end_date
    )


# ==============================
# INDIVIDUAL MACHINE ANALYTICS
# ==============================

@dashboard_bp.route('/analytics/machine/<int:machine_id>')
def machine_analytics(machine_id):

    from datetime import datetime, timedelta
    from flask import request

    period = request.args.get('period', '12months')

    today = datetime.today().date()

    if period == '30days':
        start_date = today - timedelta(days=30)

    elif period == '3months':
        start_date = today - timedelta(days=90)

    elif period == '6months':
        start_date = today - timedelta(days=180)

    elif period == 'custom':
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date or not end_date:
            start_date = today - timedelta(days=365)
            end_date = today

    else:
        start_date = today - timedelta(days=365)
        end_date = today

    if period != 'custom':
        end_date = today

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            strftime('%Y-%m', maintenance_date) AS month,
            COUNT(*) AS total
        FROM maintenance
        WHERE machine_id = ?
        AND date(maintenance_date)
            BETWEEN date(?) AND date(?)
        GROUP BY strftime('%Y-%m', maintenance_date)
        ORDER BY month
    """, (machine_id, start_date, end_date))

    rows = cursor.fetchall()

    conn.close()

    monthly_data = {
        row['month']: row['total']
        for row in rows
    }

    return monthly_data