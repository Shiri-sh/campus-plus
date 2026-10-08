from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

STUDENT = "student"
ADMIN = "admin"
ROLES = (STUDENT, ADMIN)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

MATERIAL_TYPES = (
    ("exams", "Exams"),
    ("quizzes", "Quizzes"),
    ("summaries", "Summaries"),
    ("presentations", "Presentations"),
    ("recordings", "Recordings"),
)

FILE_TYPES = (
    ("exam", "Exam"),
    ("summary", "Summary"),
    ("presentation", "Presentation"),
    ("exercise", "Exercise"),
)

ACADEMIC_YEARS = tuple(range(2026, 2017, -1))

MATERIAL_TYPE_LABELS = dict(MATERIAL_TYPES)
FILE_TYPE_LABELS = dict(FILE_TYPES)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)
    last_login_at = db.Column(db.DateTime)
    materials = db.relationship("Material", backref="uploader")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def initials(self):
        local = self.email.split("@")[0]
        return (local[:2] or "U").upper()

    @property
    def role_label(self):
        return "Administrator" if self.role == ADMIN else "Student"


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    materials = db.relationship("Material", backref="course")


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    academic_year = db.Column(db.Integer, nullable=False)
    material_type = db.Column(db.String(40), nullable=False)
    file_type = db.Column(db.String(40), nullable=False)
    icon_type = db.Column(db.String(20), nullable=False, default="pdf")
    lecturer = db.Column(db.String(255))
    uploaded_at = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)
    ai_summary = db.Column(db.Text)
    file_path = db.Column(db.String(500))
    uploader_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    confidence = db.Column(db.Integer)
    ai_recommendation = db.Column(db.String(20))

    @property
    def material_type_label(self):
        return MATERIAL_TYPE_LABELS.get(self.material_type, self.material_type)

    @property
    def file_type_label(self):
        return FILE_TYPE_LABELS.get(self.file_type, self.file_type.title())

    @property
    def icon_label(self):
        return {"slides": "PPT", "video": "VID"}.get(self.icon_type, "PDF")

    @property
    def is_link(self):
        return bool(self.file_path and self.file_path.startswith(("http://", "https://")))

    @property
    def has_stored_file(self):
        return bool(self.file_path)

    @property
    def recommendation_label(self):
        return "Approve" if self.ai_recommendation != "reject" else "Reject"


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("material.id"), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    admin_reply = db.Column(db.Text)
    replied_at = db.Column(db.DateTime)
    material = db.relationship("Material", backref="reports")
    reporter = db.relationship(User, backref="reports")
