from __future__ import annotations

from datetime import date, datetime
from typing import Any

from constants import DATE_FORMAT
from errors import ApiError


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def parse_time(value: str) -> str:
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"Invalid time '{value}'. Use HH:MM.") from exc


def parse_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"{field_name} must be a whole number.") from exc


def parse_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"{field_name} must be a number.") from exc
