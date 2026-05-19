from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any


# Simple in-memory session store. Restarting the server logs everyone out.
SESSIONS: dict[str, dict[str, Any]] = {}
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 120_000


def hash_password(password: str, salt_hex: str | None = None) -> str:
    salt_hex = salt_hex or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PASSWORD_ITERATIONS,
    )
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt_hex}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith(f"{PASSWORD_ALGORITHM}$"):
        return verify_pbkdf2_sha256(password, stored_hash)
    return verify_legacy_pbkdf2_sha256(password, stored_hash)


def verify_pbkdf2_sha256(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, expected = stored_hash.split("$", 3)
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        return False
    if algorithm != PASSWORD_ALGORITHM:
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    ).hex()
    return hmac.compare_digest(actual, expected)


def verify_legacy_pbkdf2_sha256(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, expected = stored_hash.split("$", 1)
    except ValueError:
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PASSWORD_ITERATIONS,
    ).hex()
    return hmac.compare_digest(actual, expected)


def generate_initial_password() -> str:
    return secrets.token_urlsafe(18)


def create_session(user: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = user
    return token
