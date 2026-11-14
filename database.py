
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DATABASE = Path(__file__).resolve().parent / "fixtrack.db"


def get_connection():
    connection = sqlite3.connect(str(DATABASE), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_tables():
    connection = get_connection()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS machines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_number TEXT UNIQUE NOT NULL,
                machine_name TEXT NOT NULL,
                department TEXT,
                manufacturer TEXT,
                model TEXT,
                status TEXT DEFAULT 'Active'
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS spare_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_code TEXT UNIQUE NOT NULL,
                part_name TEXT NOT NULL,
                category TEXT,
                brand TEXT,
                specification TEXT,
                current_stock INTEGER DEFAULT 0,
                reorder_level INTEGER DEFAULT 5,
                location TEXT
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS maintenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id INTEGER NOT NULL,
                spare_part_id INTEGER,
                quantity INTEGER DEFAULT 0,
                maintenance_date TEXT NOT NULL,
                remarks TEXT,
                FOREIGN KEY (machine_id)
                    REFERENCES machines(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (spare_part_id)
                    REFERENCES spare_parts(id)
                    ON DELETE SET NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
        """)

        columns = [
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        ]

        if "role" not in columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN role TEXT "
                "NOT NULL DEFAULT 'user'"
            )

        # Preserve existing admin credentials.
        # Grant admin permissions only to the existing
        # account explicitly named admin.
        connection.execute("""
            UPDATE users
            SET role = 'admin'
            WHERE username = 'admin'
        """)

        existing_admin = connection.execute(
            "SELECT id FROM users WHERE username = ?",
            ("admin",)
        ).fetchone()

        if existing_admin is None:
            raise RuntimeError(
                "Admin account not found. "
                "Restore your existing admin account "
                "before enabling role-based access."
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
