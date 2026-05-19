# Hotel Room Management - First Version

This project contains a Python REST server plus two client options:

- `server/hotel_server.py` - REST API server with SQLite database access.
- `client/hotel_client.py` - Tkinter desktop GUI client that talks to the server through HTTP.
- `web-client/` - React web GUI client that talks to the same REST API.

Only the server opens the SQLite database and room image storage. Clients never import `sqlite3` and only use REST API requests.

## Project Structure

```text
server/
  hotel_server.py      API server entry point
  api_handler.py       HTTP routing and request handlers
  database.py          SQLite connection, schema, seed data, activity log
  booking_queries.py   Booking query and billing helpers
  security.py          Password hashing and in-memory sessions
  validators.py        Shared API input validation
  constants.py         Server constants
  errors.py            API error type
  uploads/             Runtime room image storage, ignored by git

client/
  hotel_client.py      GUI client entry point
  app.py               Main Tkinter application shell
  tabs.py              Dashboard, rooms, and bookings tabs
  dialogs.py           Room, booking, and check-out dialogs
  api_client.py        REST API client
  settings.py          Reads client/.settings
  display.py           Windows DPI awareness helper
  constants.py         Client constants
  .settings            Client configuration

web-client/
  package.json         React/Vite scripts and dependencies
  public/settings.json Web client server URL setting
  src/main.jsx         React application
  src/api.js           REST API helper
  src/styles.css       Web UI styling
```

## Requirements

- Python 3.10 or newer.
- Node.js 20 or newer for the React web client.
- No third-party Python packages are required for this first version.

You can still run this command for a normal Python project setup flow:

```powershell
pip install -r requirements.txt
```

## Run

Open one terminal for the server:

```powershell
python server/hotel_server.py
```

Open another terminal for the client:

```powershell
python client/hotel_client.py
```

Or run the React web client:

```powershell
cd web-client
npm install
npm run dev
```

Then open:

```text
http://127.0.0.1:5173
```

To change which server the client connects to, edit `client/.settings`:

```text
SERVER_URL=http://127.0.0.1:8000
```

For the React web client, edit `web-client/public/settings.json`:

```json
{
  "serverUrl": "http://127.0.0.1:8000"
}
```

The React login screen also lets you override the server URL in the browser.

The server creates `server/hotel.db` automatically on first start.
Room pictures are stored under `server/uploads/rooms`.

The only seeded account is the Admin account with username `admin`. No staff accounts are created by default.

There is no default password. To choose the first Admin password yourself, set `HOTEL_ADMIN_PASSWORD` before the first server start:

```powershell
$env:HOTEL_ADMIN_PASSWORD = "change-this-before-use"
python server/hotel_server.py
```

If `HOTEL_ADMIN_PASSWORD` is not set and the Admin account needs to be created or migrated away from the old default password, the server prints a generated initial password in the server terminal.

If the Admin account already exists and you want the server to create a new password, start it with:

```powershell
python server/hotel_server.py --reset-admin-password
```

The generated password is printed in the server terminal. This flag intentionally resets the existing Admin password.

## Current Features

- Login with Admin and Staff roles.
- Modern themed desktop GUI with sidebar navigation.
- Admin-only staff account management.
- Staff shift management with admin scheduling and staff self-view.
- Room filters by type, price range, and status.
- Room amenities and double-click room details with an Additional Info section.
- Room picture upload and gallery for Admin and Staff users.
- Room list and room status updates.
- Admin-only room create, edit, and delete.
- Booking creation with guest details.
- Check-in and check-out workflow.
- Admin-only booking cancellation.
- Chart-based dashboard summary.
- React web dashboard with modern charts, cards, filters, and room media controls.
- Server-side validation for dates, room conflicts, and permissions.
- Basic activity logging on the server.

## REST API Summary

All endpoints except health and login require:

```text
Authorization: Bearer <token>
```

Main endpoints:

- `GET /api/health`
- `POST /api/login`
- `GET /api/rooms`
- `GET /api/staff` Admin only
- `POST /api/staff` Admin only
- `PUT /api/staff/{id}` Admin only
- `DELETE /api/staff/{id}` Admin only, deactivates account
- `GET /api/shifts`
- `POST /api/shifts` Admin only
- `PUT /api/shifts/{id}` Admin only
- `DELETE /api/shifts/{id}` Admin only, cancels shift
- `POST /api/rooms` Admin only
- `PUT /api/rooms/{id}` Admin only
- `PATCH /api/rooms/{id}/status`
- `GET /api/rooms/{id}/images`
- `POST /api/rooms/{id}/images` Admin and Staff
- `DELETE /api/rooms/{id}` Admin only
- `GET /api/room-images/{id}/content`
- `DELETE /api/room-images/{id}` Admin and Staff
- `GET /api/bookings`
- `POST /api/bookings`
- `POST /api/bookings/{id}/checkin`
- `POST /api/bookings/{id}/checkout`
- `POST /api/bookings/{id}/cancel` Admin only
- `GET /api/reports/summary`
- `GET /api/activity` Admin only

## Suggested Next Features

- Add staff account management in the Admin UI.
- Add invoice/receipt export.
- Add booking edit and guest history screens.
- Add password change/reset.
- Add daily housekeeping task assignment.
