import os
import uuid
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

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
from werkzeug.utils import secure_filename

from catalog import approved_materials, explorer_options, suggestion_items
from classify import ICON_BY_EXTENSION, MATERIAL_TO_FILE_TYPE, classify_source
from extensions import db, login_manager
from models import (
    ADMIN,
    ACADEMIC_YEARS,
    FILE_TYPES,
    MATERIAL_TYPES,
    ROLES,
    STATUS_APPROVED,
    STATUS_PENDING,
    STUDENT,
    Course,
    Material,
    Report,
    User,
)
from admin_views import register_admin_routes
from schema import ensure_schema
from seed import seed_catalog

app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "campus-plus-dev-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    app.instance_path, "campus_plus.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(app.instance_path, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = set(ICON_BY_EXTENSION)

db.init_app(app)
login_manager.init_app(app)

with app.app_context():
    db.create_all()
    ensure_schema()
    seed_catalog()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


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
        flash("Invalid institutional email or password.", "error")
        return render_template("auth.html", active_tab="login", form_email=email)

    if user.is_blocked:
        flash("This account has been blocked by an administrator.", "error")
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
        flash("Please choose a role: Student or Administrator.", "error")
        return render_template("auth.html", active_tab="register", form_email=email)

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return render_template("auth.html", active_tab="register", form_email=email)

    if password != confirm_password:
        flash("Password and confirmation do not match.", "error")
        return render_template("auth.html", active_tab="register", form_email=email)

    if User.query.filter_by(email=email).first():
        flash("This institutional email is already registered.", "error")
        return render_template("auth.html", active_tab="register", form_email=email)

    user = User(email=email, role=role)
    user.set_password(password)
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
            if item
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
        "academic_year": material.academic_year,
        "material_type": material.material_type_label,
        "ai_summary": material.ai_summary or "Not generated yet.",
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
        flash("Please write a report message for the administrator.", "error")
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
    flash("Report sent to the administrator.", "success")
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
            return jsonify({"error": "Upload a PDF, presentation, or document."}), 400
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
        return jsonify({"error": "Select a file or enter a video link."}), 400

    prediction = classify_source(source_name)
    session["pending_upload"]["prediction"] = prediction
    return jsonify(prediction)


@app.route("/upload/confirm", methods=["POST"])
@role_required(STUDENT)
def confirm_upload():
    pending = session.get("pending_upload")
    if not pending:
        flash("Select a file or video link first.", "error")
        return redirect(url_for("upload"))

    try:
        course_id = int(request.form.get("course_id"))
        academic_year = int(request.form.get("academic_year"))
    except (TypeError, ValueError):
        flash("Please choose a valid course and academic year.", "error")
        return redirect(url_for("upload"))

    material_type = request.form.get("material_type")
    course = db.session.get(Course, course_id)
    if course is None or academic_year not in ACADEMIC_YEARS or material_type not in dict(MATERIAL_TYPES):
        flash("Please confirm or edit the suggested classification.", "error")
        return redirect(url_for("upload"))

    file_path = pending["video_link"] or pending["stored_name"]
    prediction = pending.get("prediction") or {}
    confidence = prediction.get("confidence")
    material = Material(
        file_name=pending["original_name"] if not pending["video_link"] else "Video link",
        course_id=course.id,
        academic_year=academic_year,
        material_type=material_type,
        file_type=MATERIAL_TO_FILE_TYPE[material_type],
        icon_type=pending["icon_type"],
        uploaded_at=date.today(),
        status=STATUS_PENDING,
        file_path=file_path,
        uploader_id=current_user.id,
        confidence=confidence,
        ai_recommendation="approve" if (confidence or 0) >= 70 else "reject",
    )
    db.session.add(material)
    db.session.commit()
    session.pop("pending_upload", None)
    return render_template(
        "upload.html",
        courses=Course.query.order_by(Course.name).all(),
        years=ACADEMIC_YEARS,
        material_types=MATERIAL_TYPES,
        prediction=None,
        uploaded=True,
        pending_course=course.name,
    )


register_admin_routes(app, role_required, material_payload)


if __name__ == "__main__":
    app.run(debug=True)
