from __future__ import annotations

import json
import base64
import binascii
import secrets
import sqlite3
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from booking_queries import (
    booking_projection,
    booking_query,
    calculate_total,
    room_is_available,
)
from constants import (
    ALLOWED_ROOM_IMAGE_TYPES,
    BASE_DIR,
    BOOKING_STATUSES,
    DATE_FORMAT,
    MAX_ROOM_IMAGE_BYTES,
    PAYMENT_STATUSES,
    ROOM_IMAGE_DIR,
    ROOM_IMAGE_EXTENSIONS,
    ROOM_STATUSES,
    SHIFT_STATUSES,
)
from database import db_session, log_activity
from errors import ApiError
from security import SESSIONS, create_session, hash_password, verify_password
from validators import parse_date, parse_float, parse_int, parse_time


class HotelRequestHandler(BaseHTTPRequestHandler):
    server_version = "HotelManagementServer/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        self.handle_request("GET")

    def do_POST(self) -> None:
        self.handle_request("POST")

    def do_PUT(self) -> None:
        self.handle_request("PUT")

    def do_PATCH(self) -> None:
        self.handle_request("PATCH")

    def do_DELETE(self) -> None:
        self.handle_request("DELETE")

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")

    def send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_binary(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=300")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}

        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(400, "Request body must be valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ApiError(400, "Request body must be a JSON object.")
        return payload

    def current_user(self, conn: sqlite3.Connection) -> dict[str, Any]:
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            raise ApiError(401, "Missing bearer token.")

        token = header[len(prefix) :]
        session = SESSIONS.get(token)
        if not session:
            raise ApiError(401, "Invalid or expired session.")

        row = conn.execute(
            """
            SELECT id, username, role, full_name
            FROM users
            WHERE id = ? AND is_active = 1
            """,
            (session["id"],),
        ).fetchone()
        if row is None:
            raise ApiError(401, "User account is inactive.")
        return dict(row)

    def require_role(self, user: dict[str, Any], *roles: str) -> None:
        if user["role"] not in roles:
            raise ApiError(403, "You do not have permission for this action.")

    def handle_request(self, method: str) -> None:
        parsed_url = urlparse(self.path)
        path_parts = [part for part in parsed_url.path.strip("/").split("/") if part]
        query = parse_qs(parsed_url.query)

        try:
            with db_session() as conn:
                payload = self.read_json() if method in {"POST", "PUT", "PATCH"} else {}

                if path_parts == ["api", "health"] and method == "GET":
                    self.send_json(200, {"status": "ok"})
                    return

                if path_parts == ["api", "login"] and method == "POST":
                    self.handle_login(conn, payload)
                    return

                if (
                    len(path_parts) == 4
                    and path_parts[:2] == ["api", "room-images"]
                    and path_parts[3] == "content"
                    and method == "GET"
                ):
                    image_id = self.parse_id(path_parts[2], "room image")
                    self.send_room_image(conn, image_id)
                    return

                user = self.current_user(conn)

                if path_parts == ["api", "me"] and method == "GET":
                    self.send_json(200, {"user": user})
                elif path_parts == ["api", "me", "password"] and method == "POST":
                    self.change_password(conn, user, payload)
                elif path_parts == ["api", "rooms"] and method == "GET":
                    self.list_rooms(conn)
                elif path_parts == ["api", "rooms"] and method == "POST":
                    self.require_role(user, "admin")
                    self.create_room(conn, user, payload)
                elif len(path_parts) == 3 and path_parts[:2] == ["api", "rooms"]:
                    room_id = self.parse_id(path_parts[2], "room")
                    if method == "PUT":
                        self.require_role(user, "admin")
                        self.update_room(conn, user, room_id, payload)
                    elif method == "DELETE":
                        self.require_role(user, "admin")
                        self.delete_room(conn, user, room_id)
                    else:
                        raise ApiError(405, "Method not allowed.")
                elif (
                    len(path_parts) == 4
                    and path_parts[:2] == ["api", "rooms"]
                    and path_parts[3] == "status"
                    and method == "PATCH"
                ):
                    room_id = self.parse_id(path_parts[2], "room")
                    self.update_room_status(conn, user, room_id, payload)
                elif (
                    len(path_parts) == 4
                    and path_parts[:2] == ["api", "rooms"]
                    and path_parts[3] == "cover-image"
                    and method == "PATCH"
                ):
                    room_id = self.parse_id(path_parts[2], "room")
                    self.require_role(user, "admin", "staff")
                    self.update_room_cover_image(conn, user, room_id, payload)
                elif (
                    len(path_parts) == 4
                    and path_parts[:2] == ["api", "rooms"]
                    and path_parts[3] == "images"
                ):
                    room_id = self.parse_id(path_parts[2], "room")
                    if method == "GET":
                        self.list_room_images(conn, room_id)
                    elif method == "POST":
                        self.require_role(user, "admin", "staff")
                        self.add_room_image(conn, user, room_id, payload)
                    else:
                        raise ApiError(405, "Method not allowed.")
                elif len(path_parts) == 3 and path_parts[:2] == ["api", "room-images"]:
                    image_id = self.parse_id(path_parts[2], "room image")
                    if method == "DELETE":
                        self.require_role(user, "admin", "staff")
                        self.delete_room_image(conn, user, image_id)
                    else:
                        raise ApiError(405, "Method not allowed.")
                elif path_parts == ["api", "bookings"] and method == "GET":
                    self.list_bookings(conn, query)
                elif path_parts == ["api", "bookings"] and method == "POST":
                    self.create_booking(conn, user, payload)
                elif len(path_parts) == 4 and path_parts[:2] == ["api", "bookings"]:
                    booking_id = self.parse_id(path_parts[2], "booking")
                    self.handle_booking_action(conn, user, booking_id, path_parts[3], method, payload)
                elif path_parts == ["api", "reports", "summary"] and method == "GET":
                    self.summary_report(conn, user)
                elif path_parts == ["api", "staff"] and method == "GET":
                    self.require_role(user, "admin")
                    self.list_staff(conn)
                elif path_parts == ["api", "staff"] and method == "POST":
                    self.require_role(user, "admin")
                    self.create_staff(conn, user, payload)
                elif (
                    len(path_parts) == 4
                    and path_parts[:2] == ["api", "staff"]
                    and path_parts[3] == "delete"
                    and method == "POST"
                ):
                    self.require_role(user, "admin")
                    staff_id = self.parse_id(path_parts[2], "staff")
                    self.delete_staff(conn, user, staff_id)
                elif len(path_parts) == 3 and path_parts[:2] == ["api", "staff"]:
                    self.require_role(user, "admin")
                    staff_id = self.parse_id(path_parts[2], "staff")
                    if method == "PUT":
                        self.update_staff(conn, user, staff_id, payload)
                    elif method == "DELETE":
                        self.deactivate_staff(conn, user, staff_id)
                    else:
                        raise ApiError(405, "Method not allowed.")
                elif path_parts == ["api", "shifts"] and method == "GET":
                    self.list_shifts(conn, user, query)
                elif path_parts == ["api", "shifts"] and method == "POST":
                    self.require_role(user, "admin")
                    self.create_shift(conn, user, payload)
                elif len(path_parts) == 3 and path_parts[:2] == ["api", "shifts"]:
                    self.require_role(user, "admin")
                    shift_id = self.parse_id(path_parts[2], "shift")
                    if method == "PUT":
                        self.update_shift(conn, user, shift_id, payload)
                    elif method == "DELETE":
                        self.cancel_shift(conn, user, shift_id)
                    else:
                        raise ApiError(405, "Method not allowed.")
                elif path_parts == ["api", "activity"] and method == "GET":
                    self.require_role(user, "admin")
                    self.list_activity(conn, query)
                else:
                    raise ApiError(404, "Endpoint not found.")
        except ApiError as exc:
            self.send_json(exc.status, {"error": exc.message})
        except sqlite3.IntegrityError as exc:
            self.send_json(409, {"error": f"Database constraint failed: {exc}"})
        except Exception as exc:
            self.send_json(500, {"error": f"Unexpected server error: {exc}"})

    def handle_booking_action(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        booking_id: int,
        action: str,
        method: str,
        payload: dict[str, Any],
    ) -> None:
        if method != "POST":
            raise ApiError(405, "Method not allowed.")
        if action == "checkin":
            self.check_in_booking(conn, user, booking_id)
        elif action == "checkout":
            self.check_out_booking(conn, user, booking_id, payload)
        elif action == "cancel":
            self.require_role(user, "admin")
            self.cancel_booking(conn, user, booking_id)
        else:
            raise ApiError(404, "Endpoint not found.")

    def parse_id(self, value: str, label: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise ApiError(400, f"Invalid {label} id.") from exc

    def handle_login(self, conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        if not username or not password:
            raise ApiError(400, "Username and password are required.")

        row = conn.execute(
            """
            SELECT id, username, password_hash, role, full_name
            FROM users
            WHERE username = ? AND is_active = 1
            """,
            (username,),
        ).fetchone()

        if row is None or not verify_password(password, row["password_hash"]):
            raise ApiError(401, "Invalid username or password.")

        user = {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "full_name": row["full_name"],
        }
        token = create_session(user)
        log_activity(conn, user, "login", "user", user["id"])
        self.send_json(200, {"token": token, "user": user})

    def change_password(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        current_password = str(payload.get("current_password", ""))
        new_password = str(payload.get("new_password", ""))
        if not current_password or not new_password:
            raise ApiError(400, "Current password and new password are required.")
        if len(new_password) < 8:
            raise ApiError(400, "Password must be at least 8 characters.")

        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
        if row is None or not verify_password(current_password, row["password_hash"]):
            raise ApiError(401, "Current password is incorrect.")

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user["id"]),
        )
        log_activity(conn, user, "update", "user", user["id"], "password")
        self.send_json(200, {"message": "Password updated."})

    def list_rooms(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT
                r.id,
                r.number,
                r.room_type,
                r.floor,
                r.capacity,
                r.price_per_night,
                r.status,
                r.amenities,
                r.notes,
                COUNT(ri.id) AS image_count,
                COALESCE(valid_cover.id, MIN(ri.id)) AS cover_image_id
            FROM rooms r
            LEFT JOIN room_images valid_cover
                ON valid_cover.id = r.cover_image_id AND valid_cover.room_id = r.id
            LEFT JOIN room_images ri ON ri.room_id = r.id
            GROUP BY
                r.id,
                r.number,
                r.room_type,
                r.floor,
                r.capacity,
                r.price_per_night,
                r.status,
                r.amenities,
                r.notes,
                r.cover_image_id,
                valid_cover.id
            ORDER BY CAST(r.number AS INTEGER), r.number
            """
        ).fetchall()
        rooms = []
        for row in rows:
            room = dict(row)
            cover_id = room.get("cover_image_id")
            room["cover_image_url"] = f"/api/room-images/{cover_id}/content" if cover_id else None
            rooms.append(room)
        self.send_json(200, {"rooms": rooms})

    def clean_staff_payload(
        self,
        payload: dict[str, Any],
        require_password: bool,
    ) -> dict[str, Any]:
        username = str(payload.get("username", "")).strip()
        full_name = str(payload.get("full_name", "")).strip()
        password = str(payload.get("password", ""))
        is_active = 1 if bool(payload.get("is_active", True)) else 0

        if not username:
            raise ApiError(400, "Username is required.")
        if not full_name:
            raise ApiError(400, "Full name is required.")
        if require_password and not password:
            raise ApiError(400, "Password is required.")
        if password and len(password) < 8:
            raise ApiError(400, "Password must be at least 8 characters.")

        return {
            "username": username,
            "full_name": full_name,
            "password": password,
            "is_active": is_active,
        }

    def list_staff(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT id, username, full_name, is_active, created_at
            FROM users
            WHERE role = 'staff'
              AND username NOT LIKE 'deleted_staff_%'
            ORDER BY is_active DESC, username
            """
        ).fetchall()
        self.send_json(200, {"staff": [dict(row) for row in rows]})

    def create_staff(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        values = self.clean_staff_payload(payload, require_password=True)
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, full_name, is_active)
            VALUES (?, ?, 'staff', ?, ?)
            """,
            (
                values["username"],
                hash_password(values["password"]),
                values["full_name"],
                values["is_active"],
            ),
        )
        log_activity(conn, user, "create", "staff", cursor.lastrowid, values["username"])
        self.send_json(201, {"staff_id": cursor.lastrowid})

    def update_staff(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        staff_id: int,
        payload: dict[str, Any],
    ) -> None:
        existing = conn.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'staff'",
            (staff_id,),
        ).fetchone()
        if existing is None:
            raise ApiError(404, "Staff account not found.")

        values = self.clean_staff_payload(payload, require_password=False)
        if values["password"]:
            conn.execute(
                """
                UPDATE users
                SET username = ?, full_name = ?, password_hash = ?, is_active = ?
                WHERE id = ? AND role = 'staff'
                """,
                (
                    values["username"],
                    values["full_name"],
                    hash_password(values["password"]),
                    values["is_active"],
                    staff_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET username = ?, full_name = ?, is_active = ?
                WHERE id = ? AND role = 'staff'
                """,
                (values["username"], values["full_name"], values["is_active"], staff_id),
            )
        log_activity(conn, user, "update", "staff", staff_id, values["username"])
        self.send_json(200, {"message": "Staff account updated."})

    def deactivate_staff(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        staff_id: int,
    ) -> None:
        cursor = conn.execute(
            "UPDATE users SET is_active = 0 WHERE id = ? AND role = 'staff'",
            (staff_id,),
        )
        if cursor.rowcount == 0:
            raise ApiError(404, "Staff account not found.")
        log_activity(conn, user, "deactivate", "staff", staff_id)
        self.send_json(200, {"message": "Staff account deactivated."})

    def delete_staff(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        staff_id: int,
    ) -> None:
        if staff_id == user["id"]:
            raise ApiError(400, "You cannot delete your own account.")

        row = conn.execute(
            "SELECT id, username FROM users WHERE id = ? AND role = 'staff'",
            (staff_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "Staff account not found.")

        has_scheduled_shift = conn.execute(
            "SELECT id FROM shifts WHERE staff_id = ? AND status = 'scheduled' LIMIT 1",
            (staff_id,),
        ).fetchone()
        if has_scheduled_shift:
            raise ApiError(409, "Staff has scheduled shifts and cannot be deleted.")

        anonymized_username = f"deleted_staff_{staff_id}_{secrets.token_hex(4)}"
        conn.execute(
            """
            UPDATE users
            SET username = ?,
                full_name = 'Former Staff',
                password_hash = ?,
                is_active = 0
            WHERE id = ? AND role = 'staff'
            """,
            (anonymized_username, hash_password(secrets.token_hex(16)), staff_id),
        )

        log_activity(conn, user, "delete", "staff", staff_id, row["username"])
        self.send_json(200, {"message": "Staff credentials wiped."})

    def clean_shift_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        staff_id = parse_int(payload.get("staff_id", 0), "Staff ID")
        shift_date = parse_date(str(payload.get("shift_date", "")).strip()).strftime(DATE_FORMAT)
        start_time = parse_time(str(payload.get("start_time", "")).strip())
        end_time = parse_time(str(payload.get("end_time", "")).strip())
        status = str(payload.get("status", "scheduled")).strip()
        notes = str(payload.get("notes", "")).strip()

        if status not in SHIFT_STATUSES:
            valid_statuses = ", ".join(sorted(SHIFT_STATUSES))
            raise ApiError(400, f"Shift status must be one of: {valid_statuses}")
        if end_time <= start_time:
            raise ApiError(400, "Shift end time must be after start time.")

        return {
            "staff_id": staff_id,
            "shift_date": shift_date,
            "start_time": start_time,
            "end_time": end_time,
            "status": status,
            "notes": notes,
        }

    def ensure_staff_exists(self, conn: sqlite3.Connection, staff_id: int) -> None:
        row = conn.execute(
            """
            SELECT id
            FROM users
            WHERE id = ? AND role = 'staff' AND is_active = 1
            """,
            (staff_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "Active staff account not found.")

    def ensure_shift_available(
        self,
        conn: sqlite3.Connection,
        staff_id: int,
        shift_date: str,
        start_time: str,
        end_time: str,
        exclude_shift_id: int | None = None,
    ) -> None:
        params: list[Any] = [staff_id, shift_date, start_time, end_time]
        extra_filter = ""
        if exclude_shift_id is not None:
            extra_filter = "AND id <> ?"
            params.append(exclude_shift_id)

        row = conn.execute(
            f"""
            SELECT id
            FROM shifts
            WHERE staff_id = ?
              AND shift_date = ?
              AND status <> 'cancelled'
              AND ? < end_time
              AND ? > start_time
              {extra_filter}
            LIMIT 1
            """,
            params,
        ).fetchone()
        if row is not None:
            raise ApiError(409, "Shift overlaps an existing shift.")

    def list_shifts(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        query: dict[str, list[str]],
    ) -> None:
        filters: list[str] = []
        params: list[Any] = []

        if user["role"] == "staff":
            filters.append("s.staff_id = ?")
            params.append(user["id"])
        else:
            staff_id = query.get("staff_id", [""])[0]
            if staff_id:
                filters.append("s.staff_id = ?")
                params.append(parse_int(staff_id, "Staff ID"))

        status = query.get("status", [""])[0]
        if status:
            if status not in SHIFT_STATUSES:
                raise ApiError(400, "Invalid shift status filter.")
            filters.append("s.status = ?")
            params.append(status)

        shift_date = query.get("date", [""])[0]
        if shift_date:
            filters.append("s.shift_date = ?")
            params.append(parse_date(shift_date).strftime(DATE_FORMAT))

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        rows = conn.execute(
            f"""
            SELECT
                s.id,
                s.staff_id,
                u.username AS staff_username,
                u.full_name AS staff_name,
                s.shift_date,
                s.start_time,
                s.end_time,
                s.status,
                s.notes,
                s.created_at
            FROM shifts s
            JOIN users u ON u.id = s.staff_id
            {where_clause}
            ORDER BY s.shift_date DESC, s.start_time, u.full_name
            """,
            params,
        ).fetchall()
        self.send_json(200, {"shifts": [dict(row) for row in rows]})

    def create_shift(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        values = self.clean_shift_payload(payload)
        self.ensure_staff_exists(conn, values["staff_id"])
        self.ensure_shift_available(
            conn,
            values["staff_id"],
            values["shift_date"],
            values["start_time"],
            values["end_time"],
        )
        cursor = conn.execute(
            """
            INSERT INTO shifts (staff_id, shift_date, start_time, end_time, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                values["staff_id"],
                values["shift_date"],
                values["start_time"],
                values["end_time"],
                values["status"],
                values["notes"],
            ),
        )
        log_activity(conn, user, "create", "shift", cursor.lastrowid, values["shift_date"])
        self.send_json(201, {"shift_id": cursor.lastrowid})

    def update_shift(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        shift_id: int,
        payload: dict[str, Any],
    ) -> None:
        if conn.execute("SELECT id FROM shifts WHERE id = ?", (shift_id,)).fetchone() is None:
            raise ApiError(404, "Shift not found.")

        values = self.clean_shift_payload(payload)
        self.ensure_staff_exists(conn, values["staff_id"])
        self.ensure_shift_available(
            conn,
            values["staff_id"],
            values["shift_date"],
            values["start_time"],
            values["end_time"],
            exclude_shift_id=shift_id,
        )
        conn.execute(
            """
            UPDATE shifts
            SET staff_id = ?,
                shift_date = ?,
                start_time = ?,
                end_time = ?,
                status = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                values["staff_id"],
                values["shift_date"],
                values["start_time"],
                values["end_time"],
                values["status"],
                values["notes"],
                shift_id,
            ),
        )
        log_activity(conn, user, "update", "shift", shift_id, values["shift_date"])
        self.send_json(200, {"message": "Shift updated."})

    def cancel_shift(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        shift_id: int,
    ) -> None:
        cursor = conn.execute(
            """
            UPDATE shifts
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (shift_id,),
        )
        if cursor.rowcount == 0:
            raise ApiError(404, "Shift not found.")
        log_activity(conn, user, "cancel", "shift", shift_id)
        self.send_json(200, {"message": "Shift cancelled."})

    def clean_room_payload(self, payload: dict[str, Any], partial: bool = False) -> dict[str, Any]:
        required = ["number", "room_type", "floor", "capacity", "price_per_night", "status"]
        if not partial:
            missing = [field for field in required if payload.get(field) in (None, "")]
            if missing:
                raise ApiError(400, f"Missing fields: {', '.join(missing)}")

        values: dict[str, Any] = {}
        if "number" in payload:
            values["number"] = str(payload["number"]).strip()
        if "room_type" in payload:
            values["room_type"] = str(payload["room_type"]).strip()
        if "floor" in payload:
            values["floor"] = parse_int(payload["floor"], "Floor")
        if "capacity" in payload:
            values["capacity"] = parse_int(payload["capacity"], "Capacity")
        if "price_per_night" in payload:
            values["price_per_night"] = parse_float(payload["price_per_night"], "Price")
        if "status" in payload:
            status = str(payload["status"]).strip()
            if status not in ROOM_STATUSES:
                valid_statuses = ", ".join(sorted(ROOM_STATUSES))
                raise ApiError(400, f"Room status must be one of: {valid_statuses}")
            values["status"] = status
        if "amenities" in payload:
            values["amenities"] = str(payload["amenities"]).strip()
        if "notes" in payload:
            values["notes"] = str(payload["notes"]).strip()

        if values.get("floor", 1) < 0:
            raise ApiError(400, "Floor cannot be negative.")
        if values.get("capacity", 1) <= 0:
            raise ApiError(400, "Capacity must be greater than zero.")
        if values.get("price_per_night", 1) < 0:
            raise ApiError(400, "Price cannot be negative.")

        return values

    def create_room(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        values = self.clean_room_payload(payload)
        cursor = conn.execute(
            """
            INSERT INTO rooms (
                number, room_type, floor, capacity, price_per_night, status, amenities, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["number"],
                values["room_type"],
                values["floor"],
                values["capacity"],
                values["price_per_night"],
                values["status"],
                values.get("amenities", ""),
                values.get("notes", ""),
            ),
        )
        log_activity(conn, user, "create", "room", cursor.lastrowid, values["number"])
        self.send_json(201, {"room_id": cursor.lastrowid})

    def update_room(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        room_id: int,
        payload: dict[str, Any],
    ) -> None:
        if conn.execute("SELECT id FROM rooms WHERE id = ?", (room_id,)).fetchone() is None:
            raise ApiError(404, "Room not found.")

        values = self.clean_room_payload(payload, partial=True)
        if not values:
            raise ApiError(400, "No room fields supplied.")

        assignments = ", ".join(f"{field} = ?" for field in values)
        params = list(values.values()) + [room_id]
        conn.execute(
            f"UPDATE rooms SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            params,
        )
        log_activity(conn, user, "update", "room", room_id)
        self.send_json(200, {"message": "Room updated."})

    def update_room_status(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        room_id: int,
        payload: dict[str, Any],
    ) -> None:
        status = str(payload.get("status", "")).strip()
        if status not in ROOM_STATUSES:
            valid_statuses = ", ".join(sorted(ROOM_STATUSES))
            raise ApiError(400, f"Room status must be one of: {valid_statuses}")

        cursor = conn.execute(
            """
            UPDATE rooms
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, room_id),
        )
        if cursor.rowcount == 0:
            raise ApiError(404, "Room not found.")

        log_activity(conn, user, "status", "room", room_id, status)
        self.send_json(200, {"message": "Room status updated."})

    def update_room_cover_image(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        room_id: int,
        payload: dict[str, Any],
    ) -> None:
        self.ensure_room_exists(conn, room_id)
        image_id = parse_int(payload.get("image_id"), "Image ID")
        if image_id <= 0:
            raise ApiError(400, "Image ID must be greater than zero.")

        row = conn.execute(
            """
            SELECT id
            FROM room_images
            WHERE id = ? AND room_id = ?
            """,
            (image_id, room_id),
        ).fetchone()
        if row is None:
            raise ApiError(404, "Room image not found for this room.")

        conn.execute(
            """
            UPDATE rooms
            SET cover_image_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (image_id, room_id),
        )
        log_activity(conn, user, "cover", "room_image", image_id, f"room_id={room_id}")
        self.send_json(200, {"message": "Room display picture updated."})

    def ensure_room_exists(self, conn: sqlite3.Connection, room_id: int) -> None:
        if conn.execute("SELECT id FROM rooms WHERE id = ?", (room_id,)).fetchone() is None:
            raise ApiError(404, "Room not found.")

    def room_image_projection(self, row: sqlite3.Row, cover_image_id: int | None = None) -> dict[str, Any]:
        image = dict(row)
        image["url"] = f"/api/room-images/{image['id']}/content"
        image["is_cover"] = image["id"] == cover_image_id
        return image

    def list_room_images(self, conn: sqlite3.Connection, room_id: int) -> None:
        self.ensure_room_exists(conn, room_id)
        cover_image_id = self.resolve_room_cover_image_id(conn, room_id)
        rows = conn.execute(
            """
            SELECT
                ri.id,
                ri.room_id,
                ri.file_name,
                ri.content_type,
                ri.created_at,
                u.username AS uploaded_by_username,
                u.full_name AS uploaded_by_name
            FROM room_images ri
            LEFT JOIN users u ON u.id = ri.uploaded_by
            WHERE ri.room_id = ?
            ORDER BY ri.id DESC
            """,
            (room_id,),
        ).fetchall()
        self.send_json(
            200,
            {"images": [self.room_image_projection(row, cover_image_id) for row in rows]},
        )

    def resolve_room_cover_image_id(self, conn: sqlite3.Connection, room_id: int) -> int | None:
        room = conn.execute(
            "SELECT cover_image_id FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
        if room is None:
            return None

        cover_image_id = room["cover_image_id"]
        if cover_image_id is not None:
            row = conn.execute(
                "SELECT id FROM room_images WHERE id = ? AND room_id = ?",
                (cover_image_id, room_id),
            ).fetchone()
            if row is not None:
                return row["id"]

        row = conn.execute(
            "SELECT MIN(id) AS id FROM room_images WHERE room_id = ?",
            (room_id,),
        ).fetchone()
        return row["id"] if row and row["id"] is not None else None

    def add_room_image(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        room_id: int,
        payload: dict[str, Any],
    ) -> None:
        self.ensure_room_exists(conn, room_id)
        image = self.clean_room_image_payload(payload)
        extension = ROOM_IMAGE_EXTENSIONS[image["content_type"]]
        room_dir = ROOM_IMAGE_DIR / str(room_id)
        room_dir.mkdir(parents=True, exist_ok=True)
        stored_path = room_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(8)}{extension}"
        stored_path.write_bytes(image["data"])

        try:
            cursor = conn.execute(
                """
                INSERT INTO room_images (room_id, file_name, content_type, stored_path, uploaded_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    room_id,
                    image["file_name"],
                    image["content_type"],
                    stored_path.relative_to(BASE_DIR).as_posix(),
                    user["id"],
                ),
            )
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise

        if self.resolve_room_cover_image_id(conn, room_id) is None:
            conn.execute(
                """
                UPDATE rooms
                SET cover_image_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (cursor.lastrowid, room_id),
            )

        row = conn.execute(
            """
            SELECT
                ri.id,
                ri.room_id,
                ri.file_name,
                ri.content_type,
                ri.created_at,
                u.username AS uploaded_by_username,
                u.full_name AS uploaded_by_name
            FROM room_images ri
            LEFT JOIN users u ON u.id = ri.uploaded_by
            WHERE ri.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        log_activity(conn, user, "upload", "room_image", cursor.lastrowid, f"room_id={room_id}")
        self.send_json(201, {"image": self.room_image_projection(row, self.resolve_room_cover_image_id(conn, room_id))})

    def delete_room_image(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        image_id: int,
    ) -> None:
        row = conn.execute(
            """
            SELECT id, room_id, file_name, stored_path
            FROM room_images
            WHERE id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "Room image not found.")

        conn.execute("DELETE FROM room_images WHERE id = ?", (image_id,))
        conn.execute(
            """
            UPDATE rooms
            SET cover_image_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE cover_image_id = ?
            """,
            (image_id,),
        )
        image_path = self.resolve_room_image_path(row["stored_path"])
        try:
            image_path.unlink(missing_ok=True)
        except OSError as exc:
            raise ApiError(500, "Room image file could not be deleted.") from exc

        log_activity(conn, user, "delete", "room_image", image_id, f"room_id={row['room_id']}")
        self.send_json(200, {"message": "Room image deleted."})

    def send_room_image(self, conn: sqlite3.Connection, image_id: int) -> None:
        row = conn.execute(
            """
            SELECT content_type, stored_path
            FROM room_images
            WHERE id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "Room image not found.")

        image_path = self.resolve_room_image_path(row["stored_path"])
        if not image_path.exists() or not image_path.is_file():
            raise ApiError(404, "Room image file not found.")
        self.send_binary(200, image_path.read_bytes(), row["content_type"])

    def resolve_room_image_path(self, stored_path: str) -> Path:
        image_path = (BASE_DIR / stored_path).resolve()
        image_root = ROOM_IMAGE_DIR.resolve()
        try:
            image_path.relative_to(image_root)
        except ValueError as exc:
            raise ApiError(404, "Room image not found.") from exc
        return image_path

    def clean_room_image_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_data = payload.get("data_base64") or payload.get("data")
        if not isinstance(raw_data, str) or not raw_data.strip():
            raise ApiError(400, "Image data is required.")

        content_type = str(payload.get("content_type", "")).split(";", 1)[0].strip().lower()
        raw_data = raw_data.strip()
        if raw_data.startswith("data:"):
            try:
                header, raw_data = raw_data.split(",", 1)
            except ValueError as exc:
                raise ApiError(400, "Image data URL is invalid.") from exc
            detected_header_type = header[5:].split(";", 1)[0].strip().lower()
            if detected_header_type:
                content_type = detected_header_type

        if content_type not in ALLOWED_ROOM_IMAGE_TYPES:
            allowed = ", ".join(sorted(ALLOWED_ROOM_IMAGE_TYPES))
            raise ApiError(400, f"Room image must be one of: {allowed}")

        try:
            image_data = base64.b64decode(raw_data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ApiError(400, "Image data must be valid base64.") from exc

        if not image_data:
            raise ApiError(400, "Image data cannot be empty.")
        if len(image_data) > MAX_ROOM_IMAGE_BYTES:
            limit_mb = MAX_ROOM_IMAGE_BYTES // (1024 * 1024)
            raise ApiError(400, f"Room image cannot exceed {limit_mb} MB.")

        detected_type = self.detect_image_content_type(image_data)
        if detected_type != content_type:
            raise ApiError(400, "Image data does not match the declared content type.")

        return {
            "file_name": self.sanitize_file_name(str(payload.get("file_name", "room-image"))),
            "content_type": content_type,
            "data": image_data,
        }

    def sanitize_file_name(self, file_name: str) -> str:
        name = Path(file_name).name.strip() or "room-image"
        safe_name = "".join(
            char if char.isascii() and (char.isalnum() or char in {"-", "_", ".", " "}) else "_"
            for char in name
        )
        safe_name = " ".join(safe_name.split())
        return safe_name[:120] or "room-image"

    def detect_image_content_type(self, image_data: bytes) -> str | None:
        if image_data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if len(image_data) >= 12 and image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP":
            return "image/webp"
        return None

    def delete_room(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        room_id: int,
    ) -> None:
        has_booking = conn.execute(
            "SELECT id FROM bookings WHERE room_id = ? LIMIT 1",
            (room_id,),
        ).fetchone()
        if has_booking:
            raise ApiError(409, "Rooms with booking history cannot be deleted.")

        cursor = conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        if cursor.rowcount == 0:
            raise ApiError(404, "Room not found.")

        log_activity(conn, user, "delete", "room", room_id)
        self.send_json(200, {"message": "Room deleted."})

    def list_bookings(self, conn: sqlite3.Connection, query: dict[str, list[str]]) -> None:
        filters: list[str] = []
        params: list[Any] = []

        status = query.get("status", [""])[0]
        if status:
            if status not in BOOKING_STATUSES:
                raise ApiError(400, "Invalid booking status filter.")
            filters.append("b.status = ?")
            params.append(status)

        today_filter = query.get("today", [""])[0]
        if today_filter:
            today = date.today().strftime(DATE_FORMAT)
            filters.append("(b.check_in = ? OR b.check_out = ?)")
            params.extend([today, today])

        search = query.get("search", [""])[0].strip()
        if search:
            filters.append("(g.full_name LIKE ? OR g.phone LIKE ? OR r.number LIKE ?)")
            term = f"%{search}%"
            params.extend([term, term, term])

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        rows = conn.execute(
            f"{booking_query()} {where_clause} ORDER BY b.check_in DESC, b.id DESC",
            params,
        ).fetchall()
        self.send_json(200, {"bookings": [booking_projection(row) for row in rows]})

    def create_booking(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        room_id = parse_int(payload.get("room_id", 0), "Room ID")
        check_in = str(payload.get("check_in", "")).strip()
        check_out = str(payload.get("check_out", "")).strip()
        deposit = parse_float(payload.get("deposit", 0) or 0, "Deposit")
        payment_status = str(payload.get("payment_status", "unpaid")).strip()
        guest = payload.get("guest", {})

        if not isinstance(guest, dict):
            raise ApiError(400, "Guest must be an object.")
        if payment_status not in PAYMENT_STATUSES:
            raise ApiError(400, "Invalid payment status.")
        if deposit < 0:
            raise ApiError(400, "Deposit cannot be negative.")

        check_in_date = parse_date(check_in)
        check_out_date = parse_date(check_out)
        if check_out_date <= check_in_date:
            raise ApiError(400, "Check-out date must be after check-in date.")

        room = conn.execute(
            "SELECT id, status FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
        if room is None:
            raise ApiError(404, "Room not found.")
        if room["status"] == "maintenance":
            raise ApiError(409, "Room is under maintenance.")
        if not room_is_available(conn, room_id, check_in, check_out):
            raise ApiError(409, "Room already has an active booking for those dates.")

        guest_name = str(guest.get("full_name", "")).strip()
        guest_phone = str(guest.get("phone", "")).strip()
        if not guest_name or not guest_phone:
            raise ApiError(400, "Guest name and phone are required.")

        guest_cursor = conn.execute(
            """
            INSERT INTO guests (full_name, phone, email, document_id, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                guest_name,
                guest_phone,
                str(guest.get("email", "")).strip(),
                str(guest.get("document_id", "")).strip(),
                str(guest.get("notes", "")).strip(),
            ),
        )

        booking_cursor = conn.execute(
            """
            INSERT INTO bookings (
                guest_id, room_id, check_in, check_out, status, deposit, payment_status
            )
            VALUES (?, ?, ?, ?, 'reserved', ?, ?)
            """,
            (guest_cursor.lastrowid, room_id, check_in, check_out, deposit, payment_status),
        )

        if check_in_date <= date.today() and room["status"] == "available":
            conn.execute(
                """
                UPDATE rooms
                SET status = 'reserved', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (room_id,),
            )

        log_activity(conn, user, "create", "booking", booking_cursor.lastrowid, guest_name)
        self.send_json(201, {"booking_id": booking_cursor.lastrowid})

    def load_booking(self, conn: sqlite3.Connection, booking_id: int) -> sqlite3.Row:
        row = conn.execute(
            f"{booking_query()} WHERE b.id = ?",
            (booking_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "Booking not found.")
        return row

    def check_in_booking(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        booking_id: int,
    ) -> None:
        booking = self.load_booking(conn, booking_id)
        if booking["status"] != "reserved":
            raise ApiError(409, "Only reserved bookings can be checked in.")

        room_status = conn.execute(
            "SELECT status FROM rooms WHERE id = ?",
            (booking["room_id"],),
        ).fetchone()["status"]
        if room_status in {"occupied", "maintenance"}:
            raise ApiError(409, f"Room is currently {room_status}.")

        conn.execute(
            """
            UPDATE bookings
            SET status = 'checked_in', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (booking_id,),
        )
        conn.execute(
            """
            UPDATE rooms
            SET status = 'occupied', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (booking["room_id"],),
        )
        log_activity(conn, user, "checkin", "booking", booking_id)
        self.send_json(200, {"message": "Guest checked in."})

    def check_out_booking(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        booking_id: int,
        payload: dict[str, Any],
    ) -> None:
        booking = self.load_booking(conn, booking_id)
        if booking["status"] != "checked_in":
            raise ApiError(409, "Only checked-in bookings can be checked out.")

        extra_charges = parse_float(payload.get("extra_charges", 0) or 0, "Extra charges")
        payment_status = str(payload.get("payment_status", "paid")).strip()
        if extra_charges < 0:
            raise ApiError(400, "Extra charges cannot be negative.")
        if payment_status not in PAYMENT_STATUSES:
            raise ApiError(400, "Invalid payment status.")

        conn.execute(
            """
            UPDATE bookings
            SET status = 'completed',
                extra_charges = ?,
                payment_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (extra_charges, payment_status, booking_id),
        )
        conn.execute(
            """
            UPDATE rooms
            SET status = 'cleaning', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (booking["room_id"],),
        )

        updated_booking = self.load_booking(conn, booking_id)
        total_amount = calculate_total(updated_booking)
        log_activity(conn, user, "checkout", "booking", booking_id, f"total={total_amount}")
        self.send_json(
            200,
            {
                "message": "Guest checked out.",
                "total_amount": total_amount,
                "balance_due": round(total_amount - float(updated_booking["deposit"]), 2),
            },
        )

    def cancel_booking(
        self,
        conn: sqlite3.Connection,
        user: dict[str, Any],
        booking_id: int,
    ) -> None:
        booking = self.load_booking(conn, booking_id)
        if booking["status"] not in {"reserved", "checked_in"}:
            raise ApiError(409, "Only active bookings can be cancelled.")

        conn.execute(
            """
            UPDATE bookings
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (booking_id,),
        )
        if booking["status"] == "checked_in":
            conn.execute(
                """
                UPDATE rooms
                SET status = 'cleaning', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (booking["room_id"],),
            )
        log_activity(conn, user, "cancel", "booking", booking_id)
        self.send_json(200, {"message": "Booking cancelled."})

    def summary_report(self, conn: sqlite3.Connection, user: dict[str, Any]) -> None:
        today = date.today().strftime(DATE_FORMAT)
        room_counts = {
            row["status"]: row["count"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS count FROM rooms GROUP BY status"
            ).fetchall()
        }
        arrivals = conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE check_in = ? AND status = 'reserved'",
            (today,),
        ).fetchone()[0]
        departures = conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE check_out = ? AND status = 'checked_in'",
            (today,),
        ).fetchone()[0]

        report: dict[str, Any] = {
            "date": today,
            "rooms": room_counts,
            "arrivals_today": arrivals,
            "departures_today": departures,
        }

        if user["role"] == "admin":
            rows = conn.execute(f"{booking_query()} WHERE b.status = 'completed'").fetchall()
            report["completed_revenue"] = round(sum(calculate_total(row) for row in rows), 2)
            report["active_bookings"] = conn.execute(
                "SELECT COUNT(*) FROM bookings WHERE status IN ('reserved', 'checked_in')"
            ).fetchone()[0]

        self.send_json(200, {"summary": report})

    def list_activity(self, conn: sqlite3.Connection, query: dict[str, list[str]]) -> None:
        limit = min(parse_int(query.get("limit", ["50"])[0], "Limit"), 200)
        rows = conn.execute(
            """
            SELECT
                a.id,
                COALESCE(u.username, 'system') AS username,
                a.action,
                a.entity,
                a.entity_id,
                a.details,
                a.created_at
            FROM activity_logs a
            LEFT JOIN users u ON u.id = a.user_id
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        self.send_json(200, {"activity": [dict(row) for row in rows]})
