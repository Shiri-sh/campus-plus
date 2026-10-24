import logging
import os
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError
from werkzeug.utils import secure_filename

from catalog import approved_materials, explorer_options, suggestion_items
from classify import ICON_BY_EXTENSION, classify_source
from commands.materials import confirm_pending_upload
from db_config import resolve_database_url
from extensions import csrf, db, login_manager
from models import (
    ADMIN,
    ACADEMIC_YEARS,
    FILE_TYPES,
    MATERIAL_TYPES,
    ROLES,
    STATUS_APPROVED,
    STUDENT,
    Course,
    Material,
    Report,
    User,
    hebrew_year,
)
from admin_views import register_admin_routes
from schema import ensure_schema
from seed import seed_catalog

load_dotenv()

DEFAULT_SECRET_KEY = "campus-plus-dev-key"


def debug_enabled():
    value = os.environ.get("FLASK_DEBUG")
    if value is None:
        return True
    return value.strip().lower() in {"1", "true", "yes"}


app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or DEFAULT_SECRET_KEY

# DATABASE_URL, or all of DB_*, or local SQLite. A partial DB_* set raises.
app.config["SQLALCHEMY_DATABASE_URI"] = resolve_database_url(
    os.environ, app.instance_path
)
if app.config["SECRET_KEY"] == DEFAULT_SECRET_KEY and not debug_enabled():
    logging.getLogger("campusplus").warning(
        "SECRET_KEY is the default development value. "
        "Set a strong SECRET_KEY in the environment before running with debug disabled."
    )
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(app.instance_path, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = set(ICON_BY_EXTENSION)

db.init_app(app)
csrf.init_app(app)
login_manager.init_app(app)

CSRF_FAILURE_MESSAGE = (
    "פג תוקף ההפעלה או שהטופס אינו תקף. רעננו את העמוד ונסו שוב."
)

with app.app_context():
    db.create_all()
    ensure_schema()
    seed_catalog()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def _csrf_error_wants_json():
    if request.path == "/upload/classify":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    if _csrf_error_wants_json():
        return jsonify({"error": CSRF_FAILURE_MESSAGE}), 400
    flash(CSRF_FAILURE_MESSAGE, "error")
    return redirect(request.referrer or url_for("auth"))


def home_for(user):
    if user.role == ADMIN:
        return url_for("admin")
    return url_for("student_dashboard")


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                return redirect(home_for(current_user))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def normalize_email(value):
    return (value or "").strip().lower()


@app.route("/", methods=["GET"])
def auth():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    return render_template("auth.html", active_tab="login", form_email="")


@app.route("/login", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))

    email = normalize_email(request.form.get("email"))
    password = request.form.get("password") or ""
    user = User.query.filter_by(email=email).first()

    if user is None or not user.check_password(password):
        flash("כתובת דוא״ל מוסדית או סיסמה שגויים.", "error")
        return render_template("auth.html", active_tab="login", form_email=email)

    if user.is_blocked:
        flash("חשבון זה נחסם על ידי מנהל/ת.", "error")
        return render_template("auth.html", active_tab="login", form_email=email)

    user.last_login_at = datetime.utcnow()
    db.session.commit()
    login_user(user)
    return redirect(home_for(user))


@app.route("/register", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))

    email = normalize_email(request.form.get("email"))
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    role = request.form.get("role") or ""

    if role not in ROLES:
        flash("יש לבחור תפקיד: סטודנט/ית או מנהל/ת.", "error")
        return render_template("auth.html", active_tab="register", form_email=email)

    if len(password) < 8:
        flash("הסיסמה חייבת להכיל לפחות 8 תווים.", "error")
        return render_template("auth.html", active_tab="register", form_email=email)

    if password != confirm_password:
        flash("הסיסמה ואימות הסיסמה אינם תואמים.", "error")
        return render_template("auth.html", active_tab="register", form_email=email)

    if User.query.filter_by(email=email).first():
        flash("כתובת דוא״ל מוסדית זו כבר רשומה במערכת.", "error")
        return render_template("auth.html", active_tab="register", form_email=email)

    user = User(email=email, role=role)
    user.set_password(password)
    user.last_login_at = datetime.utcnow()
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return redirect(home_for(user))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth"))


def dashboard_query(**updates):
    args = {
        "q": request.args.get("q", ""),
        "file_type": request.args.get("file_type", ""),
        "course": request.args.get("course", ""),
        "year": request.args.get("year", ""),
        "type": request.args.get("type", ""),
    }
    args.update(updates)
    return {key: value for key, value in args.items() if value not in (None, "")}


@app.context_processor
def inject_dashboard_url():
    def student_url(**updates):
        return url_for("student_dashboard", **dashboard_query(**updates))

    return {
        "student_url": student_url,
        "file_types": FILE_TYPES,
        "search_query": request.args.get("q", ""),
        "hebrew_year": hebrew_year,
    }


@app.route("/student")
@role_required(STUDENT)
def student_dashboard():
    query = request.args.get("q", "").strip()
    try:
        course_id = int(request.args.get("course")) if request.args.get("course") else None
    except ValueError:
        course_id = None
    try:
        year = int(request.args.get("year")) if request.args.get("year") else None
    except ValueError:
        year = None
    material_type = request.args.get("type") or None
    file_type = request.args.get("file_type") or None

    if query and not course_id:
        exact_course = Course.query.filter(Course.name.ilike(query)).first()
        if exact_course:
            course_id = exact_course.id

    materials, inferred_year, inferred_file_type = approved_materials(
        course_id=course_id,
        year=year,
        material_type=material_type,
        file_type=file_type,
        query=query,
    )
    options = explorer_options()
    selected_course = None
    if course_id:
        selected_course = next((item for item in options["courses"] if str(item.id) == str(course_id)), None)

    years = options["years"]
    if selected_course:
        course_years = [
            item
            for (item,) in db.session.query(Material.academic_year)
            .filter_by(course_id=selected_course.id, status=STATUS_APPROVED)
            .distinct()
            .all()
            if item is not None
        ]
        if course_years:
            years = tuple(sorted(course_years, reverse=True))

    return render_template(
        "student_dashboard.html",
        materials=materials,
        courses=options["courses"],
        years=years,
        material_types=options["material_types"],
        file_types=options["file_types"],
        courses_with_files=options["courses_with_files"],
        selected_course=selected_course,
        selected_year=year,
        selected_type=material_type,
        selected_file_type=file_type or inferred_file_type,
        search_query=query,
    )


@app.route("/student/suggest")
@role_required(STUDENT)
def student_suggest():
    return jsonify(suggestion_items(request.args.get("q", "")))


def approved_material_or_404(material_id):
    material = db.session.get(Material, material_id)
    if material is None or material.status != STATUS_APPROVED:
        abort(404)
    return material


def material_payload(material):
    preview_kind = "none"
    preview_url = ""
    if material.is_link and "drive.google.com" in material.file_path:
        preview_kind = "file"
        preview_url = material.file_path
    elif material.is_link and "docs.google.com" in material.file_path:
        preview_kind = "file"
        preview_url = material.file_path
    elif material.is_link:
        preview_kind = "video"
        preview_url = material.file_path
    elif material.file_path:
        preview_kind = "file"
        preview_url = url_for(
            "preview_material" if material.status == STATUS_APPROVED else "admin_file",
            material_id=material.id,
        )

    download_url = ""
    if material.file_path:
        if material.status == STATUS_APPROVED:
            download_url = url_for("download_material", material_id=material.id)
        else:
            download_url = url_for("admin_file", material_id=material.id)

    return {
        "id": material.id,
        "file_name": material.file_name,
        "course": material.course.name,
        "lecturer": material.lecturer or "—",
        "academic_year": hebrew_year(material.academic_year),
        "material_type": material.material_type_label,
        "ai_summary": material.ai_summary or "עדיין לא נוצר.",
        "preview_kind": preview_kind,
        "preview_url": preview_url,
        "download_url": download_url,
    }


@app.route("/student/materials/<int:material_id>")
@role_required(STUDENT)
def material_details(material_id):
    return jsonify(material_payload(approved_material_or_404(material_id)))


@app.route("/student/materials/<int:material_id>/preview")
@role_required(STUDENT)
def preview_material(material_id):
    material = approved_material_or_404(material_id)
    if not material.file_path:
        abort(404)
    if material.is_link:
        return redirect(material.file_path)
    return send_from_directory(app.config["UPLOAD_FOLDER"], Path(material.file_path).name)


@app.route("/student/materials/<int:material_id>/download")
@role_required(STUDENT)
def download_material(material_id):
    material = approved_material_or_404(material_id)
    if not material.file_path:
        abort(404)
    if material.is_link:
        return redirect(material.file_path)
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        Path(material.file_path).name,
        as_attachment=True,
        download_name=material.file_name,
    )


@app.route("/student/materials/<int:material_id>/report", methods=["POST"])
@role_required(STUDENT)
def report_material(material_id):
    material = approved_material_or_404(material_id)
    message = (request.form.get("message") or "").strip()
    if not message:
        flash("יש לכתוב הודעה למנהל/ת.", "error")
        return redirect(url_for("student_dashboard"))

    report = Report(
        material_id=material.id,
        reporter_id=current_user.id,
        message=message,
        created_at=datetime.utcnow(),
        status="open",
    )
    db.session.add(report)
    db.session.commit()
    flash("הדיווח נשלח למנהל/ת.", "success")
    return redirect(url_for("student_dashboard"))


def stored_upload_name(filename):
    suffix = Path(filename).suffix.lower()
    return f"{uuid.uuid4().hex}{suffix}"


def is_video_link(value):
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@app.route("/upload")
@role_required(STUDENT)
def upload():
    return render_template(
        "upload.html",
        courses=Course.query.order_by(Course.name).all(),
        years=ACADEMIC_YEARS,
        material_types=MATERIAL_TYPES,
        prediction=None,
        uploaded=False,
    )


@app.route("/upload/classify", methods=["POST"])
@role_required(STUDENT)
def classify_upload():
    uploaded = request.files.get("file")
    video_link = (request.form.get("video_link") or "").strip()
    source_name = ""

    if uploaded and uploaded.filename:
        suffix = Path(uploaded.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return jsonify({"error": "יש להעלות PDF, מצגת או מסמך."}), 400
        saved_name = stored_upload_name(uploaded.filename)
        uploaded.save(os.path.join(app.config["UPLOAD_FOLDER"], saved_name))
        original_name = secure_filename(uploaded.filename) or saved_name
        session["pending_upload"] = {
            "stored_name": saved_name,
            "original_name": original_name,
            "icon_type": ICON_BY_EXTENSION[suffix],
            "video_link": "",
        }
        source_name = uploaded.filename
    elif is_video_link(video_link):
        session["pending_upload"] = {
            "stored_name": "",
            "original_name": video_link,
            "icon_type": "video",
            "video_link": video_link,
        }
        source_name = video_link
    else:
        return jsonify({"error": "יש לבחור קובץ או להזין קישור לסרטון."}), 400

    prediction = classify_source(source_name)
    session["pending_upload"]["prediction"] = prediction
    return jsonify(prediction)


@app.route("/upload/confirm", methods=["POST"])
@role_required(STUDENT)
def confirm_upload():
    pending = session.get("pending_upload")
    if not pending:
        flash("יש לבחור קובץ או קישור לסרטון.", "error")
        return redirect(url_for("upload"))

    try:
        course_id = int(request.form.get("course_id"))
        academic_year = int(request.form.get("academic_year"))
    except (TypeError, ValueError):
        flash("יש לבחור קורס ושנה אקדמית תקפים.", "error")
        return redirect(url_for("upload"))

    material_type = request.form.get("material_type")
    if db.session.get(Course, course_id) is None or academic_year not in ACADEMIC_YEARS or material_type not in dict(MATERIAL_TYPES):
        flash("יש לאשר או לערוך את הסיווג המוצע.", "error")
        return redirect(url_for("upload"))

    notify_key = pending.get("stored_name") or pending.get("video_link") or pending.get("original_name")
    notified = list(session.get("notified_uploads") or [])
    already_notified = notify_key in notified
    session.pop("pending_upload", None)

    try:
        material = confirm_pending_upload(
            pending,
            course_id=course_id,
            academic_year=academic_year,
            material_type=material_type,
            uploader_id=current_user.id,
            admin_approvals_url=url_for("admin", tab="approvals", _external=True),
            already_notified=already_notified,
        )
    except ValueError:
        flash("יש לאשר או לערוך את הסיווג המוצע.", "error")
        return redirect(url_for("upload"))

    if notify_key and notify_key not in notified:
        notified.append(notify_key)
        session["notified_uploads"] = notified[-20:]

    return render_template(
        "upload.html",
        courses=Course.query.order_by(Course.name).all(),
        years=ACADEMIC_YEARS,
        material_types=MATERIAL_TYPES,
        prediction=None,
        uploaded=True,
        pending_course=material.course.name,
    )


register_admin_routes(app, role_required, material_payload)


if __name__ == "__main__":
    app.run(debug=debug_enabled())
