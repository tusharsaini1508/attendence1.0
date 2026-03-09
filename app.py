import base64
import csv
import io
import os
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "attendance.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-in-production")
app.config["MAX_CONTENT_LENGTH"] = 7 * 1024 * 1024
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


def _database_url() -> str:
    env_url = os.environ.get("DATABASE_URL", "").strip()
    if not env_url:
        # Local development fallback.
        # On serverless platforms, writeable disk is typically /tmp only.
        if os.environ.get("VERCEL") == "1":
            return "sqlite:////tmp/attendance.db"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{DB_PATH.as_posix()}"
    if env_url.startswith("postgres://"):
        env_url = f"postgresql://{env_url[len('postgres://'):]}"
    if env_url.startswith("postgresql://"):
        env_url = f"postgresql+psycopg://{env_url[len('postgresql://'):]}"
    return env_url


app.config["SQLALCHEMY_DATABASE_URI"] = _database_url()
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    attendance_entries = db.relationship(
        "Attendance", backref="submitted_by", lazy=True, cascade="all, delete-orphan"
    )


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.Index("idx_attendance_user_created_at", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    person_name = db.Column(db.String(120), nullable=False)
    # Vercel has ephemeral filesystem, so image is stored in DB as data URL.
    photo_data = db.Column(db.Text)
    # Legacy fallback for old local DB rows before Vercel migration.
    photo_path = db.Column(db.String(255))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    location_text = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


def init_db() -> None:
    with app.app_context():
        db.create_all()
        _run_legacy_migrations()
        admin_exists = User.query.filter_by(username="admin").first()
        if not admin_exists:
            admin = User(
                full_name="System Administrator",
                username="admin",
                password_hash=generate_password_hash("Admin@123"),
                role="admin",
            )
            db.session.add(admin)
            db.session.commit()


def _run_legacy_migrations() -> None:
    inspector = inspect(db.engine)
    if "attendance" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("attendance")}
    if "photo_data" not in columns:
        db.session.execute(text("ALTER TABLE attendance ADD COLUMN photo_data TEXT"))
        db.session.commit()

    # Performance index for frequent dashboard and duplicate-check queries.
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_attendance_user_created_at "
            "ON attendance (user_id, created_at)"
        )
    )
    db.session.commit()


def now_utc() -> datetime:
    return datetime.utcnow()


def day_range_utc(value: datetime):
    start = value.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def current_user():
    if hasattr(g, "_current_user"):
        return g._current_user

    user_id = session.get("user_id")
    if not user_id:
        g._current_user = None
        return None

    user = db.session.get(User, user_id)
    g._current_user = user
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        if not current_user():
            session.clear()
            flash("Session expired. Please login again.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        if user.role != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)

    return wrapper


@app.context_processor
def inject_template_context():
    return {"session_user": current_user()}


def format_dt(dt_value: datetime) -> str:
    if dt_value is None:
        return ""
    if isinstance(dt_value, str):
        return dt_value
    return dt_value.strftime("%Y-%m-%d %H:%M:%S")


def attendance_to_dict(entry: Attendance):
    photo_src = entry.photo_data
    if not photo_src and entry.photo_path:
        photo_src = url_for("static", filename=entry.photo_path)

    submitted_by = entry.submitted_by
    if submitted_by:
        user_full_name = submitted_by.full_name
        username = submitted_by.username
    else:
        user_full_name = "Deleted User"
        username = "deleted"

    return {
        "id": entry.id,
        "person_name": entry.person_name,
        "photo_src": photo_src,
        "latitude": entry.latitude,
        "longitude": entry.longitude,
        "location_text": entry.location_text,
        "created_at": format_dt(entry.created_at),
        "user_full_name": user_full_name,
        "username": username,
    }


@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if not full_name or not username or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("register.html")
        if User.query.filter_by(username=username).first():
            flash("Username already exists. Try another one.", "danger")
            return render_template("register.html")

        new_user = User(
            full_name=full_name,
            username=username,
            password_hash=generate_password_hash(password),
            role="user",
        )
        try:
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Username already exists. Try another one.", "danger")
            return render_template("register.html")

        flash("Account created successfully. You can now login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid username or password.", "danger")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user.id
        flash(f"Welcome back, {user.full_name}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if not user:
        session.clear()
        flash("Session expired. Please login again.", "warning")
        return redirect(url_for("login"))

    now_value = now_utc()
    start_day, end_day = day_range_utc(now_value)

    if user.role == "admin":
        stats = {
            "total_users": User.query.count(),
            "total_records": Attendance.query.count(),
            "today_records": Attendance.query.filter(
                Attendance.created_at >= start_day, Attendance.created_at < end_day
            ).count(),
        }
        entries = (
            Attendance.query.options(joinedload(Attendance.submitted_by))
            .order_by(Attendance.created_at.desc())
            .limit(500)
            .all()
        )
    else:
        stats = {
            "total_records": Attendance.query.filter_by(user_id=user.id).count(),
            "today_records": Attendance.query.filter(
                Attendance.user_id == user.id,
                Attendance.created_at >= start_day,
                Attendance.created_at < end_day,
            ).count(),
        }
        entries = (
            Attendance.query.options(joinedload(Attendance.submitted_by))
            .filter_by(user_id=user.id)
            .order_by(Attendance.created_at.desc())
            .limit(50)
            .all()
        )

    records = [attendance_to_dict(item) for item in entries]
    return render_template(
        "dashboard.html",
        user={"id": user.id, "full_name": user.full_name, "username": user.username, "role": user.role},
        is_admin=user.role == "admin",
        stats=stats,
        records=records,
    )


def _validate_and_normalize_image(image_data: str) -> str:
    if not image_data or "," not in image_data:
        raise ValueError("Invalid image payload.")

    meta, encoded = image_data.split(",", 1)
    meta = meta.strip().lower()
    allowed_prefixes = ("data:image/jpeg;base64", "data:image/jpg;base64", "data:image/png;base64", "data:image/webp;base64")

    if not any(meta.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError("Unsupported image format.")

    try:
        binary = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Invalid image payload.") from exc

    if len(binary) < 1000:
        raise ValueError("Captured image is too small.")
    if len(binary) > 6 * 1024 * 1024:
        raise ValueError("Captured image is too large.")

    if meta.startswith("data:image/png;base64"):
        mime = "image/png"
    elif meta.startswith("data:image/webp;base64"):
        mime = "image/webp"
    else:
        mime = "image/jpeg"

    clean_base64 = base64.b64encode(binary).decode("ascii")
    return f"data:{mime};base64,{clean_base64}"


@app.route("/attendance", methods=["POST"])
@login_required
def submit_attendance():
    payload = request.get_json(silent=True) or {}
    person_name = payload.get("person_name", "").strip()
    image_data = payload.get("image_data", "")
    location_text = payload.get("location_text", "").strip()
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")

    if not person_name:
        return jsonify({"ok": False, "error": "Name is required."}), 400
    if len(person_name) > 120:
        return jsonify({"ok": False, "error": "Name is too long."}), 400
    if not image_data:
        return jsonify({"ok": False, "error": "Photo capture is required."}), 400
    if latitude is None or longitude is None:
        return jsonify({"ok": False, "error": "Location is required."}), 400

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid location values."}), 400

    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return jsonify({"ok": False, "error": "Location coordinates are out of range."}), 400

    try:
        normalized_image_data = _validate_and_normalize_image(image_data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    user = current_user()
    if not user:
        session.clear()
        return jsonify({"ok": False, "error": "Session expired. Please login again."}), 401

    now_value = now_utc()
    start_day, end_day = day_range_utc(now_value)

    already_marked = Attendance.query.filter(
        Attendance.user_id == user.id,
        Attendance.created_at >= start_day,
        Attendance.created_at < end_day,
    ).first()
    if already_marked:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Attendance already submitted for today.",
                }
            ),
            409,
        )

    entry = Attendance(
        user_id=user.id,
        person_name=person_name,
        photo_data=normalized_image_data,
        # Keeps backward compatibility with old SQLite schema where photo_path is NOT NULL.
        photo_path="db-inline",
        latitude=latitude,
        longitude=longitude,
        location_text=location_text or None,
        created_at=now_value,
    )
    try:
        db.session.add(entry)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return (
            jsonify({"ok": False, "error": "Attendance already submitted for today."}),
            409,
        )
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"ok": False, "error": "Unable to save attendance right now."}), 500

    return jsonify({"ok": True, "message": "Attendance submitted.", "created_at": format_dt(now_value)})


@app.route("/admin/attendance/<int:attendance_id>/delete", methods=["POST"])
@admin_required
def delete_attendance(attendance_id: int):
    try:
        deleted = Attendance.query.filter_by(id=attendance_id).delete(
            synchronize_session=False
        )
        if deleted == 0:
            flash("Attendance record not found.", "warning")
            return redirect(url_for("dashboard"))
        db.session.commit()
        flash("Attendance record deleted.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Unable to delete attendance right now. Please retry.", "danger")
    return redirect(url_for("dashboard"))


@app.route("/admin/export")
@admin_required
def export_attendance():
    rows = (
        Attendance.query.options(joinedload(Attendance.submitted_by))
        .order_by(Attendance.created_at.desc())
        .all()
    )

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(
        [
            "Attendance ID",
            "Person Name",
            "Submitted By",
            "Username",
            "Latitude",
            "Longitude",
            "Location Text",
            "Timestamp",
        ]
    )
    for row in rows:
        submitted_by = row.submitted_by
        submitted_by_name = submitted_by.full_name if submitted_by else "Deleted User"
        submitted_by_username = submitted_by.username if submitted_by else "deleted"
        writer.writerow(
            [
                row.id,
                row.person_name,
                submitted_by_name,
                submitted_by_username,
                row.latitude,
                row.longitude,
                row.location_text or "",
                format_dt(row.created_at),
            ]
        )

    payload = io.BytesIO(csv_buffer.getvalue().encode("utf-8"))
    payload.seek(0)
    filename = f"attendance_export_{date.today().isoformat()}.csv"
    return send_file(
        payload,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


init_db()

if __name__ == "__main__":
    app.run(debug=True)
