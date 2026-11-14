
import sqlite3
from pathlib import Path
from datetime import datetime

# =====================================================
# CONFIGURATION
# =====================================================

BASE_DIR = Path(__file__).resolve().parent

SOURCE_DB = BASE_DIR / "PPPL_Backup_2026-10-27_18-11.db"
TARGET_DB = BASE_DIR / "fixtrack.db"

# Safety setting: must be explicitly enabled to import.
CONFIRM_IMPORT = True


# =====================================================
# HELPERS
# =====================================================

def connect_database(path, readonly=False):
    if readonly:
        connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro",
            uri=True
        )
    else:
        connection = sqlite3.connect(path)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def get_columns(connection, table):
    return {
        row["name"]
        for row in connection.execute(
            f"PRAGMA table_info({table})"
        )
    }


def validate_database(source, target):
    required_source = {
        "machines": {
            "id", "machine_number", "machine_type",
            "department", "manufacturer", "model", "status"
        },
        "spare_parts": {
            "id", "part_code", "part_name", "category",
            "brand", "specification", "current_stock",
            "reorder_level", "location"
        },
        "maintenance": {
            "id", "machine_id", "maintenance_date",
            "problem", "work_done", "remarks"
        },
        "maintenance_parts": {
            "maintenance_id", "part_id", "quantity"
        }
    }

    required_target = {
        "machines": {
            "id", "machine_number", "machine_name",
            "department", "manufacturer", "model", "status"
        },
        "spare_parts": {
            "id", "part_code", "part_name", "category",
            "brand", "specification", "current_stock",
            "reorder_level", "location"
        },
        "maintenance": {
            "id", "machine_id", "spare_part_id",
            "quantity", "maintenance_date", "remarks"
        },
        "users": {"id", "username", "password"}
    }

    for table, columns in required_source.items():
        missing = columns - get_columns(source, table)
        if missing:
            raise ValueError(
                f"PPPL table '{table}' is missing: {sorted(missing)}"
            )

    for table, columns in required_target.items():
        missing = columns - get_columns(target, table)
        if missing:
            raise ValueError(
                f"FixTrack table '{table}' is missing: {sorted(missing)}"
            )


def create_backup(target):
    backup_name = (
        "fixtrack_before_pppl_import_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + ".db"
    )

    backup_path = BASE_DIR / backup_name

    with sqlite3.connect(backup_path) as backup:
        target.backup(backup)

    return backup_path


def combine_remarks(record):
    parts = []

    for label, field in [
        ("Problem", "problem"),
        ("Work Done", "work_done"),
        ("Remarks", "remarks")
    ]:
        value = record[field]
        if value and str(value).strip():
            parts.append(f"{label}: {value}")

    return " | ".join(parts) or "Imported from PPPL"


# =====================================================
# IMPORT
# =====================================================

def import_data(source, target):
    stats = {
        "machines": 0,
        "spare_parts": 0,
        "maintenance": 0,
        "skipped_machines": 0,
        "skipped_parts": 0,
        "skipped_maintenance": 0,
        "multiple_parts": 0
    }

    machine_ids = {}
    part_ids = {}

    target.execute("BEGIN IMMEDIATE")

    try:
        # Clear test records in dependency order.
        target.execute("DELETE FROM maintenance")
        target.execute("DELETE FROM spare_parts")
        target.execute("DELETE FROM machines")

        # -------------------------
        # MACHINES
        # -------------------------

        machines = source.execute(
            "SELECT * FROM machines ORDER BY id"
        ).fetchall()

        for machine in machines:
            number = str(machine["machine_number"] or "").strip()
            machine_type = str(machine["machine_type"] or "").strip()

            if not number or not machine_type:
                stats["skipped_machines"] += 1
                continue

            try:
                cursor = target.execute(
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
                        number,
                        machine_type,
                        machine["department"],
                        machine["manufacturer"],
                        machine["model"],
                        machine["status"] or "Active"
                    )
                )

                machine_ids[machine["id"]] = cursor.lastrowid
                stats["machines"] += 1

            except sqlite3.IntegrityError:
                stats["skipped_machines"] += 1

        # -------------------------
        # SPARE PARTS
        # -------------------------

        spare_parts = source.execute(
            "SELECT * FROM spare_parts ORDER BY id"
        ).fetchall()

        for part in spare_parts:
            code = str(part["part_code"] or "").strip()
            name = str(part["part_name"] or "").strip()

            if not code or not name:
                stats["skipped_parts"] += 1
                continue

            try:
                cursor = target.execute(
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
                        code,
                        name,
                        part["category"],
                        part["brand"],
                        part["specification"],
                        part["current_stock"] or 0,
                        part["reorder_level"] if
                        part["reorder_level"] is not None else 5,
                        part["location"]
                    )
                )

                part_ids[part["id"]] = cursor.lastrowid
                stats["spare_parts"] += 1

            except sqlite3.IntegrityError:
                stats["skipped_parts"] += 1

        # -------------------------
        # MAINTENANCE
        # -------------------------

        maintenance_records = source.execute(
            "SELECT * FROM maintenance ORDER BY id"
        ).fetchall()

        for record in maintenance_records:
            new_machine_id = machine_ids.get(record["machine_id"])

            if new_machine_id is None:
                stats["skipped_maintenance"] += 1
                continue

            usage = source.execute(
                """
                SELECT part_id, quantity
                FROM maintenance_parts
                WHERE maintenance_id = ?
                """,
                (record["id"],)
            ).fetchall()

            # Skip records with multiple spare part entries.
            if len(usage) > 1:
                stats["multiple_parts"] += 1
                stats["skipped_maintenance"] += 1
                continue

            new_part_id = None
            quantity = 0

            if len(usage) == 1:
                new_part_id = part_ids.get(usage[0]["part_id"])

                if new_part_id is None:
                    stats["skipped_maintenance"] += 1
                    continue

                quantity = usage[0]["quantity"]

                if quantity is None or quantity < 0:
                    stats["skipped_maintenance"] += 1
                    continue

            target.execute(
                """
                INSERT INTO maintenance (
                    machine_id,
                    spare_part_id,
                    quantity,
                    maintenance_date,
                    remarks
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    new_machine_id,
                    new_part_id,
                    quantity,
                    record["maintenance_date"],
                    combine_remarks(record)
                )
            )

            stats["maintenance"] += 1

        # Validate relationships before committing.
        foreign_key_errors = target.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if foreign_key_errors:
            raise ValueError(
                "Foreign key validation failed. Import rolled back."
            )

        target.commit()

    except Exception:
        target.rollback()
        raise

    return stats


# =====================================================
# MAIN
# =====================================================

def main():
    print("\nFIXTRACK - PPPL DATA IMPORT")
    print("=" * 45)

    if not SOURCE_DB.is_file():
        print(f"Source database not found:\n{SOURCE_DB}")
        return

    if not TARGET_DB.is_file():
        print(f"FixTrack database not found:\n{TARGET_DB}")
        return

    source = None
    target = None

    try:
        source = connect_database(SOURCE_DB, readonly=True)
        target = connect_database(TARGET_DB)

        validate_database(source, target)

        print("Database structures validated successfully.")

        print("\nPPPL source records:")
        for table in [
            "machines",
            "spare_parts",
            "maintenance",
            "maintenance_parts"
        ]:
            count = source.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            print(f"  {table}: {count}")

        if not CONFIRM_IMPORT:
            print(
                "\nPREVIEW ONLY. No records have been changed."
            )
            print(
                "Set CONFIRM_IMPORT = True in import_pppl.py "
                "when ready."
            )
            return

        backup_path = create_backup(target)

        print(f"\nSafety backup created:\n{backup_path}")

        stats = import_data(source, target)

        print("\nIMPORT COMPLETED")
        print("=" * 45)

        print(f"Machines imported: {stats['machines']}")
        print(f"Spare parts imported: {stats['spare_parts']}")
        print(f"Maintenance imported: {stats['maintenance']}")
        print(f"Machines skipped: {stats['skipped_machines']}")
        print(f"Spare parts skipped: {stats['skipped_parts']}")
        print(f"Maintenance skipped: {stats['skipped_maintenance']}")
        print(
            "Maintenance skipped due to multiple parts: "
            f"{stats['multiple_parts']}"
        )

        print("\nFixTrack login accounts were preserved.")
        print("Imported stock quantities were not deducted again.")

    except Exception as error:
        print(f"\nIMPORT FAILED: {error}")
        print("Check the error before retrying.")

    finally:
        if source is not None:
            source.close()

        if target is not None:
            target.close()


if __name__ == "__main__":
    main()
