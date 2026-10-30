from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user

from agent.worker import relevance_label

from catalog import (
    admin_reports,
    admin_users,
    approved_course_counts,
    courses_by_name,
    open_report_count,
    pending_materials,
    search_admin_materials,
)
from commands.materials import (
    approve_material as approve_material_record,
    delete_material as delete_material_record,
    reject_material as reject_material_record,
    update_material as update_material_record,
)
from commands.reports import reply_to_report
from commands.users import (
    create_user_by_admin,
    delete_user as delete_user_record,
    set_blocked,
    set_user_role,
)
from extensions import db
from link_download import link_download_target
from models import (
    ADMIN,
    ACADEMIC_YEARS,
    MATERIAL_TYPES,
    STATUS_APPROVED,
    STATUS_LABELS,
    STATUS_REJECTED,
    STUDENT,
    Material,
    Report,
    User,
)

MATERIAL_FILTER_KEYS = ("q", "course", "year", "type", "status")


def recommendation_for(material):
    if material.confidence is None:
        return "approve"
    return "approve" if material.confidence >= 70 else "reject"


def admin_redirect(tab):
    return redirect(url_for("admin", tab=tab))


def _optional_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def material_filters_from_request():
    material_type = request.args.get("type") or ""
    if material_type not in dict(MATERIAL_TYPES):
        material_type = ""
    status = request.args.get("status") or ""
    if status not in (STATUS_APPROVED, STATUS_REJECTED):
        status = ""
    course_id = _optional_int(request.args.get("course"))
    year = _optional_int(request.args.get("year"))
    return {
        "q": (request.args.get("q") or "").strip(),
        "course": "" if course_id is None else str(course_id),
        "year": "" if year is None else str(year),
        "type": material_type,
        "status": status,
    }


def materials_redirect():
    filters = {}
    for key in MATERIAL_FILTER_KEYS:
        value = (request.form.get(key) or "").strip()
        if value:
            filters[key] = value
    return redirect(url_for("admin", tab="materials", **filters))


def admin_material_payload(material, material_payload):
    """Admin preview modal must use admin routes, not student-only URLs."""
    payload = material_payload(material)
    if material.file_path:
        payload["download_url"] = url_for("admin_file", material_id=material.id)
    if material.file_path and not material.is_link:
        payload["preview_url"] = url_for(
            "admin_preview_material", material_id=material.id
        )
    return payload


def register_admin_routes(app, role_required, material_payload):
    def admin_material(material_id):
        material = db.session.get(Material, material_id)
        if material is None:
            abort(404)
        return material

    @app.route("/admin")
    @role_required(ADMIN)
    def admin():
        pending = pending_materials()
        for material in pending:
            if not material.ai_recommendation:
                material.ai_recommendation = recommendation_for(material)
        reports = admin_reports()
        users = admin_users()
        distribution = approved_course_counts()
        filters = material_filters_from_request()
        materials, materials_truncated = search_admin_materials(
            query=filters["q"],
            course_id=int(filters["course"]) if filters["course"] else None,
            year=int(filters["year"]) if filters["year"] else None,
            material_type=filters["type"] or None,
            status=filters["status"] or None,
        )

        return render_template(
            "admin.html",
            active_tab=request.args.get("tab") or "approvals",
            pending=pending,
            reports=reports,
            users=users,
            materials=materials,
            materials_truncated=materials_truncated,
            material_filters=filters,
            filters_active=any(filters.values()),
            courses=courses_by_name(),
            years=ACADEMIC_YEARS,
            material_types=MATERIAL_TYPES,
            status_filters=(
                (STATUS_APPROVED, STATUS_LABELS[STATUS_APPROVED]),
                (STATUS_REJECTED, STATUS_LABELS[STATUS_REJECTED]),
            ),
            pending_count=len(pending),
            open_report_count=open_report_count(),
            active_course_count=len(distribution),
            distribution=distribution,
            relevance_label=relevance_label,
        )

    @app.route("/admin/materials/<int:material_id>")
    @role_required(ADMIN)
    def admin_material_details(material_id):
        material = admin_material(material_id)
        return jsonify(admin_material_payload(material, material_payload))

    @app.route("/admin/materials/<int:material_id>/preview")
    @role_required(ADMIN)
    def admin_preview_material(material_id):
        material = admin_material(material_id)
        if not material.file_path:
            abort(404)
        if material.is_link:
            return redirect(material.file_path)
        return send_from_directory(
            current_app.config["UPLOAD_FOLDER"],
            Path(material.file_path).name,
        )

    @app.route("/admin/materials/<int:material_id>/file")
    @role_required(ADMIN)
    def admin_file(material_id):
        material = admin_material(material_id)
        if not material.file_path:
            abort(404)
        if material.is_link:
            return redirect(link_download_target(material.file_path))
        return send_from_directory(
            current_app.config["UPLOAD_FOLDER"],
            Path(material.file_path).name,
            as_attachment=True,
            download_name=material.file_name,
        )

    @app.route("/admin/materials/<int:material_id>/approve", methods=["POST"])
    @role_required(ADMIN)
    def approve_material(material_id):
        material = admin_material(material_id)
        approve_material_record(material.id, current_user.id)
        flash(f"אושר: {material.file_name}.", "success")
        return admin_redirect("approvals")

    @app.route("/admin/materials/<int:material_id>/reject", methods=["POST"])
    @role_required(ADMIN)
    def reject_material(material_id):
        material = admin_material(material_id)
        reject_material_record(material.id, current_user.id)
        flash(f"נדחה: {material.file_name}.", "success")
        return admin_redirect("approvals")

    @app.route("/admin/materials/<int:material_id>/update", methods=["POST"])
    @role_required(ADMIN)
    def update_material(material_id):
        material = admin_material(material_id)
        try:
            course_id = int(request.form.get("course_id"))
            academic_year = int(request.form.get("academic_year"))
        except (TypeError, ValueError):
            flash("יש לבחור קורס ושנה תקפים.", "error")
            return materials_redirect()
        material_type = request.form.get("material_type")
        if material_type not in dict(MATERIAL_TYPES):
            flash("יש לבחור סוג חומר תקף.", "error")
            return materials_redirect()
        material = update_material_record(
            material.id,
            current_user.id,
            file_name=request.form.get("file_name"),
            course_id=course_id,
            academic_year=academic_year,
            material_type=material_type,
            lecturer=request.form.get("lecturer"),
        )
        flash(f"עודכן: {material.file_name}.", "success")
        return materials_redirect()

    @app.route("/admin/materials/<int:material_id>/delete", methods=["POST"])
    @role_required(ADMIN)
    def delete_material(material_id):
        material = admin_material(material_id)
        delete_material_record(material.id, current_user.id)
        flash("החומר נמחק.", "success")
        return materials_redirect()

    @app.route("/admin/reports/<int:report_id>/reply", methods=["POST"])
    @role_required(ADMIN)
    def reply_report(report_id):
        report = db.session.get(Report, report_id)
        if report is None:
            abort(404)
        reply = (request.form.get("reply") or "").strip()
        if not reply:
            flash("יש לכתוב תגובה לפני שליחה.", "error")
            return admin_redirect("reports")
        reply_to_report(report.id, current_user.id, reply)
        flash(
            f"התגובה נשמרה עבור {report.reporter.email}. Gmail MCP עדיין לא מחובר — לא נשלח דוא״ל.",
            "success",
        )
        return admin_redirect("reports")

    @app.route("/admin/users/create", methods=["POST"])
    @role_required(ADMIN)
    def create_admin_user():
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if len(password) < 8:
            flash("הסיסמה חייבת להכיל לפחות 8 תווים.", "error")
            return admin_redirect("users")
        if User.query.filter_by(email=email).first():
            flash("כתובת דוא״ל מוסדית זו כבר רשומה במערכת.", "error")
            return admin_redirect("users")
        try:
            create_user_by_admin(email, password, ADMIN, current_user.id)
        except ValueError as exc:
            flash(str(exc), "error")
            return admin_redirect("users")
        flash(f"נוצר/ה מנהל/ת: {email}.", "success")
        return admin_redirect("users")

    @app.route("/admin/users/<int:user_id>/role", methods=["POST"])
    @role_required(ADMIN)
    def change_user_role(user_id):
        if user_id == current_user.id:
            flash("לא ניתן לשנות את התפקיד שלך ממסך זה.", "error")
            return admin_redirect("users")
        role = request.form.get("role") or ""
        if role not in (STUDENT, ADMIN):
            flash("יש לבחור תפקיד תקף.", "error")
            return admin_redirect("users")
        user = db.session.get(User, user_id)
        if user is None:
            abort(404)
        try:
            user = set_user_role(user.id, role, current_user.id)
        except ValueError as exc:
            if str(exc) == "cannot demote the last admin":
                flash("לא ניתן להסיר את המנהל/ת האחרון/ה.", "error")
            else:
                flash(str(exc), "error")
            return admin_redirect("users")
        flash(
            f"עודכן תפקיד {user.email} ל{'מנהל/ת' if user.role == ADMIN else 'סטודנט/ית'}.",
            "success",
        )
        return admin_redirect("users")

    @app.route("/admin/users/<int:user_id>/block", methods=["POST"])
    @role_required(ADMIN)
    def block_user(user_id):
        user = db.session.get(User, user_id)
        if user is None or user.id == current_user.id:
            flash("לא ניתן לחסום חשבון זה.", "error")
            return admin_redirect("users")
        user = set_blocked(user.id, current_user.id, not user.is_blocked)
        flash(
            f"{'נחסם' if user.is_blocked else 'בוטלה חסימת'} {user.email}.",
            "success",
        )
        return admin_redirect("users")

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @role_required(ADMIN)
    def delete_user(user_id):
        user = db.session.get(User, user_id)
        if user is None or user.id == current_user.id:
            flash("לא ניתן למחוק חשבון זה.", "error")
            return admin_redirect("users")
        if user.role == ADMIN and User.query.filter_by(role=ADMIN).count() <= 1:
            flash("לא ניתן למחוק את המנהל/ת האחרון/ה.", "error")
            return admin_redirect("users")
        delete_user_record(user.id, current_user.id)
        flash("המשתמש/ת נמחק/ה.", "success")
        return admin_redirect("users")
