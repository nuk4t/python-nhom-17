from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer

from api_handler import HotelRequestHandler
from database import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Hotel room management REST server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--reset-admin-password",
        action="store_true",
        help="Generate or apply a new admin password during startup.",
    )
    args = parser.parse_args()

    admin_bootstrap = init_db(reset_admin_password=args.reset_admin_password)
    server = ThreadingHTTPServer((args.host, args.port), HotelRequestHandler)
    print(f"Hotel server running at http://{args.host}:{args.port}")
    print("Admin username: admin")
    if admin_bootstrap.generated_password:
        if admin_bootstrap.reset_requested:
            print("Admin password was reset by startup request.")
        if admin_bootstrap.reset_default_password:
            print("The old default admin password was replaced.")
        print(f"Generated admin password: {admin_bootstrap.generated_password}")
        print("Set HOTEL_ADMIN_PASSWORD to choose this password yourself.")
    elif admin_bootstrap.used_env_password:
        if admin_bootstrap.reset_requested:
            print("Admin password was reset from HOTEL_ADMIN_PASSWORD.")
        else:
            print("Admin password loaded from HOTEL_ADMIN_PASSWORD.")
    else:
        print("Existing admin password kept. Use --reset-admin-password to generate a new one.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
