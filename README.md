# AttendFlow - Vercel-Ready Attendance System

Responsive attendance app with:
- Camera photo capture
- Auto geolocation capture
- Role-based access (`admin`, `user`)
- Admin-only export + attendance management
- Vercel-friendly persistence (no local image/filesystem dependency)

## Tech Stack
- Python 3.11+
- Flask + Flask-SQLAlchemy
- SQL database via `DATABASE_URL` (Vercel Postgres recommended)
- Vanilla JS + Jinja + modern CSS

## Local Run
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start:
   ```bash
   python app.py
   ```
3. Open:
   ```text
   http://127.0.0.1:5000
   ```

If `DATABASE_URL` is not set, local SQLite (`data/attendance.db`) is used automatically.

## Vercel Deployment (Recommended)
1. Push this project to GitHub.
2. In Vercel, import the repository.
3. In Vercel dashboard, create a Postgres database and copy its `DATABASE_URL`.
4. Set environment variables in Project Settings:
   - `DATABASE_URL` = your Vercel Postgres connection string
   - `SECRET_KEY` = long random secret string
   - `APP_TIMEZONE` = your timezone (example: `Asia/Kolkata`)
5. Deploy.

This project already includes:
- `vercel.json`
- `api/index.py` serverless entrypoint

## Default Admin Account
- Username: `admin`
- Password: `Admin@123`

Change this password immediately after first login.

## Features
- `user` can:
  - Register/login
  - Mark attendance once per day
  - Capture live photo
  - Auto-fetch current location
  - View own attendance history

- `admin` can:
  - View all attendance records
  - Search records on dashboard
  - Delete attendance records
  - Export attendance as CSV

## Architecture Notes
- Captured photos are stored in DB as data URLs for Vercel compatibility.
- Avoids local file writes that are non-persistent in serverless environments.
- Browser camera/location permissions are required to submit attendance.
- Reverse geocoding uses OpenStreetMap Nominatim when available.
