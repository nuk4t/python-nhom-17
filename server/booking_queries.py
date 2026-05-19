from __future__ import annotations

import sqlite3
from typing import Any

from validators import parse_date


def calculate_total(row: sqlite3.Row) -> float:
    nights = max(1, (parse_date(row["check_out"]) - parse_date(row["check_in"])).days)
    return round(nights * float(row["price_per_night"]) + float(row["extra_charges"]), 2)


def booking_projection(row: sqlite3.Row) -> dict[str, Any]:
    booking = dict(row)
    booking["total_amount"] = calculate_total(row)
    booking["balance_due"] = round(
        booking["total_amount"] - float(booking.get("deposit", 0)),
        2,
    )
    return booking


def booking_query() -> str:
    return """
        SELECT
            b.id,
            b.guest_id,
            b.room_id,
            b.check_in,
            b.check_out,
            b.status,
            b.deposit,
            b.extra_charges,
            b.payment_status,
            b.created_at,
            g.full_name AS guest_name,
            g.phone AS guest_phone,
            g.email AS guest_email,
            g.document_id AS guest_document_id,
            r.number AS room_number,
            r.room_type,
            r.price_per_night
        FROM bookings b
        JOIN guests g ON g.id = b.guest_id
        JOIN rooms r ON r.id = b.room_id
    """


def room_is_available(
    conn: sqlite3.Connection,
    room_id: int,
    check_in: str,
    check_out: str,
    exclude_booking_id: int | None = None,
) -> bool:
    params: list[Any] = [room_id, check_in, check_out]
    extra_filter = ""
    if exclude_booking_id is not None:
        extra_filter = "AND id <> ?"
        params.append(exclude_booking_id)

    row = conn.execute(
        f"""
        SELECT id
        FROM bookings
        WHERE room_id = ?
          AND status IN ('reserved', 'checked_in')
          AND ? < check_out
          AND ? > check_in
          {extra_filter}
        LIMIT 1
        """,
        params,
    ).fetchone()
    return row is None

