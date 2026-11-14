
from getpass import getpass
from werkzeug.security import generate_password_hash

from database import create_tables, get_connection


def main():
    create_tables()

    username = input("New username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    password = getpass("New password: ")
    confirm = getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match.")
        return

    if len(password) < 12:
        print("Password must be at least 12 characters.")
        return

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO users
                (username, password, role)
            VALUES (?, ?, ?)
            """,
            (
                username,
                generate_password_hash(password),
                "user"
            )
        )

        connection.commit()
        print("User account created successfully.")

    except Exception as error:
        connection.rollback()
        print("Account creation failed:", error)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
