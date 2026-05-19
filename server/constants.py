from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hotel.db"
UPLOAD_DIR = BASE_DIR / "uploads"
ROOM_IMAGE_DIR = UPLOAD_DIR / "rooms"
DATE_FORMAT = "%Y-%m-%d"

ROOM_STATUSES = {"available", "reserved", "occupied", "cleaning", "maintenance"}
BOOKING_STATUSES = {"reserved", "checked_in", "completed", "cancelled"}
PAYMENT_STATUSES = {"unpaid", "partial", "paid", "refunded"}
SHIFT_STATUSES = {"scheduled", "completed", "cancelled"}

MAX_ROOM_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_ROOM_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ROOM_IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
