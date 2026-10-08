from datetime import datetime

from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import func

from classify import MATERIAL_TO_FILE_TYPE
from extensions import db
from models import (
    ADMIN,
    ACADEMIC_YEARS,
    MATERIAL_TYPES,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
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
        material = admin_material(material_id)
        material.status = STATUS_APPROVED
        db.session.commit()
        flash(f"Approved {material.file_name}.", "success")
        return admin_redirect("approvals")

    @app.route("/admin/materials/<int:material_id>/reject", methods=["POST"])
    @role_required(ADMIN)
    def reject_material(material_id):
        material = admin_material(material_id)
        material.status = STATUS_REJECTED
        db.session.commit()
        flash(f"Rejected {material.file_name}.", "success")
        return admin_redirect("approvals")

    @app.route("/admin/materials/<int:material_id>/update", methods=["POST"])
    @role_required(ADMIN)
    def update_material(material_id):
        material = admin_material(material_id)
        try:
            course_id = int(request.form.get("course_id"))
            academic_year = int(request.form.get("academic_year"))
        except (TypeError, ValueError):
            flash("Choose a valid course and year.", "error")
            return admin_redirect("materials")
        material_type = request.form.get("material_type")
        if material_type not in dict(MATERIAL_TYPES):
            flash("Choose a valid material type.", "error")
            return admin_redirect("materials")
        material.file_name = (request.form.get("file_name") or material.file_name).strip()
        material.course_id = course_id
        material.academic_year = academic_year
        material.material_type = material_type
        material.file_type = MATERIAL_TO_FILE_TYPE[material_type]
        material.lecturer = (request.form.get("lecturer") or "").strip() or None
        db.session.commit()
        flash(f"Updated {material.file_name}.", "success")
        return admin_redirect("materials")

    @app.route("/admin/materials/<int:material_id>/delete", methods=["POST"])
    @role_required(ADMIN)
    def delete_material(material_id):
        material = admin_material(material_id)
        Report.query.filter_by(material_id=material.id).delete()
        db.session.delete(material)
        db.session.commit()
        flash("Material deleted.", "success")
        return admin_redirect("materials")

    @app.route("/admin/reports/<int:report_id>/reply", methods=["POST"])
    @role_required(ADMIN)
    def reply_report(report_id):
        report = db.session.get(Report, report_id)
        if report is None:
            abort(404)
        reply = (request.form.get("reply") or "").strip()
        if not reply:
            flash("Write a response before sending.", "error")
            return admin_redirect("reports")
        report.admin_reply = reply
        report.replied_at = datetime.utcnow()
        report.status = "answered"
        db.session.commit()
        flash(
            f"Reply saved for {report.reporter.email}. Gmail MCP is not connected yet, so no email was sent.",
            "success",
        )
        return admin_redirect("reports")

    @app.route("/admin/users/<int:user_id>/block", methods=["POST"])
    @role_required(ADMIN)
    def block_user(user_id):
        user = db.session.get(User, user_id)
        if user is None or user.id == current_user.id:
            flash("You cannot block this account.", "error")
            return admin_redirect("users")
        user.is_blocked = not user.is_blocked
        db.session.commit()
        flash(
            f"{'Blocked' if user.is_blocked else 'Unblocked'} {user.email}.",
            "success",
        )
        return admin_redirect("users")

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @role_required(ADMIN)
    def delete_user(user_id):
        user = db.session.get(User, user_id)
        if user is None or user.id == current_user.id:
            flash("You cannot delete this account.", "error")
            return admin_redirect("users")
        if user.role == ADMIN and User.query.filter_by(role=ADMIN).count() <= 1:
            flash("The last administrator cannot be deleted.", "error")
            return admin_redirect("users")
        Report.query.filter_by(reporter_id=user.id).delete()
        Material.query.filter_by(uploader_id=user.id).update({"uploader_id": None})
        db.session.delete(user)
        db.session.commit()
        flash("User deleted.", "success")
        return admin_redirect("users")
