Build a production-ready, responsive Attendance Management Web App for small organizations.

Core objective:
- Users should mark attendance by capturing a live photo, entering name, and auto-fetching location.
- Admin should manage records and export attendance data.

Requirements:
1. Roles and access
- Two roles: `admin` and `user`.
- `user` can register/login and submit attendance only.
- `admin` can view all attendance records, filter/search, delete/manage records, and export CSV.

2. Attendance capture flow
- Attendance form fields:
  - Person name (required)
  - Live camera photo capture using browser camera (required)
  - Auto geolocation using browser geolocation API (required; fallback message if denied)
  - Optional reverse-geocoded readable location text
- Save timestamp automatically on server.
- Store captured image in server storage and reference it in database.

3. Data model
- `users`: id, full_name, username, password_hash, role, created_at
- `attendance`: id, user_id, person_name, photo_path, latitude, longitude, location_text, created_at

4. Security and auth
- Session-based authentication.
- Password hashing (never plain-text passwords).
- Role-based route protection for admin-only pages and export endpoint.

5. Admin features
- Dashboard metrics (total users, today attendance, total records).
- Attendance table with photo preview, name, user, location, timestamp.
- Delete/manage action for records.
- Export CSV endpoint (admin only).

6. User features
- Clean attendance form.
- View only own recent submissions.
- No access to admin export/manage pages.

7. UX/UI requirements
- Mobile-first responsive layout.
- Modern visual style (custom color system, cards, gradients, clear typography hierarchy).
- Accessible labels, clear validation, toast/inline feedback.
- Fast interactions and polished camera/location widgets.

8. Tech stack preference
- Backend: Python Flask
- Database: SQLite
- Frontend: Jinja templates + vanilla JS + modern CSS
- No unnecessary heavy dependencies.

9. Deliverables
- Working app code with clear folder structure.
- Default seeded admin account documented in README.
- Setup and run instructions.
- `requirements.txt`.

Implementation quality bar:
- Keep code modular, readable, and well-structured.
- Include meaningful comments only where logic is non-obvious.
- Handle errors gracefully (camera denied, geolocation denied, bad image payload, auth failures).
- Ensure pages are responsive and usable on desktop + mobile.
