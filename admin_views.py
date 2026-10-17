from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import func

from commands import materials as material_commands
from commands import reports as report_commands
from commands import users as user_commands
from commands.errors import CommandError, NotFound
from extensions import db
from models import (
    ADMIN,
    ACADEMIC_YEARS,
    MATERIAL_TYPES,
    STATUS_APPROVED,
    STATUS_PENDING,
    Course,
    Material,
    Report,
    User,
)


def recommendation_for(material):
    if material.confidence is None:
        return "approve"
    return "approve" if material.confidence >= 70 else "reject"


def admin_redirect(tab):
    return redirect(url_for("admin", tab=tab))


def register_admin_routes(app, role_required, material_payload):
    def admin_material(material_id):
        material = db.session.get(Material, material_id)
        if material is None:
            abort(404)
        return material

    @app.route("/admin")
    @role_required(ADMIN)
    def admin():
        pending = (
            Material.query.filter_by(status=STATUS_PENDING)
            .order_by(Material.uploaded_at.desc())
            .all()
        )
        for material in pending:
            if not material.ai_recommendation:
                material.ai_recommendation = recommendation_for(material)
        reports = Report.query.order_by(Report.created_at.desc()).all()
        users = User.query.order_by(User.role, User.email).all()
        distribution = (
            db.session.query(Course.name, func.count(Material.id))
            .join(Material)
            .filter(Material.status == STATUS_APPROVED)
            .group_by(Course.name)
            .order_by(func.count(Material.id).desc())
            .limit(8)
            .all()
        )
        search = (request.args.get("q") or "").strip()
        materials = Material.query.filter(Material.status != STATUS_PENDING)
        if search:
            materials = materials.filter(Material.file_name.ilike(f"%{search}%"))
        materials = materials.order_by(Material.uploaded_at.desc()).limit(80).all()

        return render_template(
            "admin.html",
            active_tab=request.args.get("tab") or "approvals",
            pending=pending,
            reports=reports,
            users=users,
            materials=materials,
            material_search=search,
            courses=Course.query.order_by(Course.name).all(),
            years=ACADEMIC_YEARS,
            material_types=MATERIAL_TYPES,
            pending_count=len(pending),
            open_report_count=Report.query.filter_by(status="open").count(),
            active_course_count=len(distribution),
            distribution=distribution,
        )

    @app.route("/admin/materials/<int:material_id>")
    @role_required(ADMIN)
    def admin_material_details(material_id):
        return jsonify(material_payload(admin_material(material_id)))

    @app.route("/admin/materials/<int:material_id>/file")
    @role_required(ADMIN)
    def admin_file(material_id):
        material = admin_material(material_id)
        if not material.file_path:
            abort(404)
        if material.is_link:
            return redirect(material.file_path)
        return send_from_directory(
            current_app.config["UPLOAD_FOLDER"],
            Path(material.file_path).name,
            as_attachment=True,
            download_name=material.file_name,
        )

    @app.route("/admin/materials/<int:material_id>/approve", methods=["POST"])
    @role_required(ADMIN)
    def approve_material(material_id):
        try:
            material = material_commands.approve_material(material_id, current_user.id)
        except NotFound:
            abort(404)
        flash(f"אושר: {material.file_name}.", "success")
        return admin_redirect("approvals")

    @app.route("/admin/materials/<int:material_id>/reject", methods=["POST"])
    @role_required(ADMIN)
    def reject_material(material_id):
        try:
            material = material_commands.reject_material(material_id, current_user.id)
        except NotFound:
            abort(404)
        flash(f"נדחה: {material.file_name}.", "success")
        return admin_redirect("approvals")

    @app.route("/admin/materials/<int:material_id>/update", methods=["POST"])
    @role_required(ADMIN)
    def update_material(material_id):
        try:
            course_id = int(request.form.get("course_id"))
            academic_year = int(request.form.get("academic_year"))
        except (TypeError, ValueError):
            flash("יש לבחור קורס ושנה תקפים.", "error")
            return admin_redirect("materials")
        try:
            material = material_commands.update_material(
                material_id,
                current_user.id,
                file_name=request.form.get("file_name"),
                course_id=course_id,
                academic_year=academic_year,
                material_type=request.form.get("material_type"),
                lecturer=request.form.get("lecturer"),
            )
        except NotFound:
            abort(404)
        except CommandError as error:
            flash(error.message, "error")
            return admin_redirect("materials")
        flash(f"עודכן: {material.file_name}.", "success")
        return admin_redirect("materials")

    @app.route("/admin/materials/<int:material_id>/delete", methods=["POST"])
    @role_required(ADMIN)
    def delete_material(material_id):
        try:
            material_commands.delete_material(material_id, current_user.id)
        except NotFound:
            abort(404)
        flash("החומר נמחק.", "success")
        return admin_redirect("materials")

    @app.route("/admin/reports/<int:report_id>/reply", methods=["POST"])
    @role_required(ADMIN)
    def reply_report(report_id):
        try:
            report = report_commands.reply_to_report(
                report_id,
                current_user.id,
                request.form.get("reply"),
            )
        except NotFound:
            abort(404)
        except CommandError as error:
            flash(error.message, "error")
            return admin_redirect("reports")
        flash(
            f"התגובה נשמרה עבור {report.reporter.email}. Gmail MCP עדיין לא מחובר — לא נשלח דוא״ל.",
            "success",
        )
        return admin_redirect("reports")

    @app.route("/admin/users/<int:user_id>/block", methods=["POST"])
    @role_required(ADMIN)
    def block_user(user_id):
        user = db.session.get(User, user_id)
        action = user_commands.block_user
        if user is not None and user.is_blocked:
            action = user_commands.unblock_user
        try:
            user = action(user_id, current_user.id)
        except CommandError as error:
            flash(error.message, "error")
            return admin_redirect("users")
        flash(
            f"{'נחסם' if user.is_blocked else 'בוטלה חסימת'} {user.email}.",
            "success",
        )
        return admin_redirect("users")

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @role_required(ADMIN)
    def delete_user(user_id):
        try:
            user_commands.delete_user(user_id, current_user.id)
        except CommandError as error:
            flash(error.message, "error")
            return admin_redirect("users")
        flash("המשתמש/ת נמחק/ה.", "success")
        return admin_redirect("users")
