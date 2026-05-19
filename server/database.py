from __future__ import annotations

import sqlite3
import os
from dataclasses import dataclass
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from constants import DB_PATH
from security import generate_initial_password, hash_password, verify_password


@dataclass(frozen=True)
class AdminBootstrap:
    username: str = "admin"
    generated_password: str | None = None
    used_env_password: bool = False
    reset_default_password: bool = False
    reset_requested: bool = False


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    conn = connect_db()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


def init_db(reset_admin_password: bool = False) -> AdminBootstrap:
    admin_bootstrap = AdminBootstrap()
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'staff')),
                full_name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT NOT NULL UNIQUE,
                room_type TEXT NOT NULL,
                floor INTEGER NOT NULL,
                capacity INTEGER NOT NULL,
                price_per_night REAL NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'available', 'reserved', 'occupied', 'cleaning', 'maintenance'
                )),
                amenities TEXT NOT NULL DEFAULT '',
                cover_image_id INTEGER,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS guests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                document_id TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id INTEGER NOT NULL REFERENCES guests(id),
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'reserved', 'checked_in', 'completed', 'cancelled'
                )),
                deposit REAL NOT NULL DEFAULT 0,
                extra_charges REAL NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL CHECK(payment_status IN (
                    'unpaid', 'partial', 'paid', 'refunded'
                )),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                action TEXT NOT NULL,
                entity TEXT NOT NULL,
                entity_id INTEGER,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL REFERENCES users(id),
                shift_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('scheduled', 'completed', 'cancelled')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS room_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                file_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                stored_path TEXT NOT NULL UNIQUE,
                uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        ensure_column(conn, "rooms", "amenities", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "rooms", "cover_image_id", "INTEGER")

        conn.execute(
            """
            DELETE FROM activity_logs
            WHERE user_id IN (SELECT id FROM users WHERE username = 'staff' AND role = 'staff')
            """
        )
        conn.execute("DELETE FROM users WHERE username = 'staff' AND role = 'staff'")

        admin_bootstrap = ensure_admin_account(conn, reset_admin_password)

        if conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
            conn.executemany(
                """
                INSERT INTO rooms (
                    number, room_type, floor, capacity, price_per_night, status, amenities, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("101", "Standard", 1, 2, 75.0, "available", "Wi-Fi, TV, kettle", "Queen bed"),
                    ("102", "Standard", 1, 2, 75.0, "available", "Wi-Fi, TV", "Twin beds"),
                    ("201", "Deluxe", 2, 3, 110.0, "available", "Wi-Fi, balcony, minibar", "City view"),
                    ("202", "Deluxe", 2, 3, 110.0, "cleaning", "Wi-Fi, bathtub, minibar", "Needs inspection"),
                    ("301", "Suite", 3, 4, 180.0, "maintenance", "Wi-Fi, lounge, minibar, bathtub", "AC service"),
                ],
            )
    return admin_bootstrap


def ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def ensure_admin_account(
    conn: sqlite3.Connection,
    reset_admin_password: bool = False,
) -> AdminBootstrap:
    admin_password = os.environ.get("HOTEL_ADMIN_PASSWORD", "").strip()
    used_env_password = bool(admin_password)
    generated_password = None

    if not admin_password:
        admin_password = generate_initial_password()
        generated_password = admin_password

    admin_row = conn.execute(
        """
        SELECT id, password_hash
        FROM users
        WHERE username = 'admin'
        """,
    ).fetchone()

    if admin_row is None:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, full_name)
            VALUES ('admin', ?, 'admin', 'System Admin')
            """,
            (hash_password(admin_password),),
        )
        return AdminBootstrap(
            generated_password=generated_password,
            used_env_password=used_env_password,
        )

    if reset_admin_password or verify_password("admin123", admin_row["password_hash"]):
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, role = 'admin', full_name = 'System Admin', is_active = 1
            WHERE id = ?
            """,
            (hash_password(admin_password), admin_row["id"]),
        )
        return AdminBootstrap(
            generated_password=generated_password,
            used_env_password=used_env_password,
            reset_default_password=verify_password("admin123", admin_row["password_hash"]),
            reset_requested=reset_admin_password,
        )

    conn.execute(
        """
        UPDATE users
        SET role = 'admin', is_active = 1
        WHERE id = ?
        """,
        (admin_row["id"],),
    )
    return AdminBootstrap()


def log_activity(
    conn: sqlite3.Connection,
    user: dict[str, Any] | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    details: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO activity_logs (user_id, action, entity, entity_id, details)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user["id"] if user else None, action, entity, entity_id, details),
    )
