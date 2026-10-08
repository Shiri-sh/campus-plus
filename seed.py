from courses import COURSE_MAP
from extensions import db
from models import Course


def seed_catalog():
    existing = {course.name for course in Course.query.all()}
    for name in COURSE_MAP.values():
        if name not in existing:
            db.session.add(Course(name=name))
            existing.add(name)
    db.session.commit()
