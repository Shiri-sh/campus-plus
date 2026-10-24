from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import event as sa_event
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

STUDENT = "student"
ADMIN = "admin"
ROLES = (STUDENT, ADMIN)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

MATERIAL_TYPES = (
    ("exams", "מבחנים"),
    ("quizzes", "תרגילים"),
    ("summaries", "סיכומים"),
    ("presentations", "מצגות"),
    ("recordings", "הקלטות"),
)

FILE_TYPES = (
    ("exam", "מבחן"),
    ("summary", "סיכום"),
    ("presentation", "מצגת"),
    ("exercise", "תרגיל"),
)

STATUS_LABELS = {
    STATUS_PENDING: "ממתין",
    STATUS_APPROVED: "מאושר",
    STATUS_REJECTED: "דחוי",
}

REPORT_STATUS_LABELS = {
    "open": "פתוח",
    "answered": "נענה",
}

ACADEMIC_YEARS = tuple(range(2026, 2017, -1))

MATERIAL_TYPE_LABELS = dict(MATERIAL_TYPES)
FILE_TYPE_LABELS = dict(FILE_TYPES)

GREGORIAN_TO_HEBREW = {
    2017: 'תשע"ז',
    2018: 'תשע"ח',
    2019: 'תשע"ט',
    2020: 'תש"פ',
    2021: 'תשפ"א',
    2022: 'תשפ"ב',
    2023: 'תשפ"ג',
    2024: 'תשפ"ד',
    2025: 'תשפ"ה',
    2026: 'תשפ"ו',
}

HEBREW_TO_GREGORIAN = {
    "תשעז": 2017, "תשעח": 2018, "תשעט": 2019,
    "תשפ": 2020,
    "תשפא": 2021, "תשפב": 2022, "תשפג": 2023,
    "תשפד": 2024, "תשפה": 2025, "תשפו": 2026,
}


def _utc_now():
    """Naive UTC timestamp, matching the rest of the app's DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hebrew_year(gregorian):
    """Convert a Gregorian year to its Hebrew academic year string."""
    if not gregorian:
        return "לא ידוע"
    return GREGORIAN_TO_HEBREW.get(gregorian, str(gregorian))


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
        return "מנהל/ת" if self.role == ADMIN else "סטודנט/ית"


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    materials = db.relationship("Material", backref="course")


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.Unicode(255), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    academic_year = db.Column(db.Integer, nullable=False)
    material_type = db.Column(db.String(40), nullable=False)
    file_type = db.Column(db.String(40), nullable=False)
    icon_type = db.Column(db.String(20), nullable=False, default="pdf")
    lecturer = db.Column(db.Unicode(255))
    uploaded_at = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)
    ai_summary = db.Column(db.UnicodeText)
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
        return "אישור" if self.ai_recommendation != "reject" else "דחייה"

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def hebrew_year_label(self):
        return hebrew_year(self.academic_year)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("material.id"), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.UnicodeText, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    admin_reply = db.Column(db.UnicodeText)
    replied_at = db.Column(db.DateTime)
    material = db.relationship("Material", backref="reports")
    reporter = db.relationship(User, backref="reports")

    @property
    def status_label(self):
        return REPORT_STATUS_LABELS.get(self.status, self.status)


class Event(db.Model):
    """Append-only audit row. Current tables stay the source of truth."""

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(60), nullable=False)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    # NVARCHAR so Hebrew values inside the JSON survive MSSQL.
    payload = db.Column(db.UnicodeText)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_now)


def _reject_event_mutation(_mapper, _connection, _target):
    raise RuntimeError("Event rows are append-only")


sa_event.listens_for(Event, "before_update")(_reject_event_mutation)
sa_event.listens_for(Event, "before_delete")(_reject_event_mutation)
