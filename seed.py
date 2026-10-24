from courses import COURSE_MAP, LEGACY_ENGLISH_NAMES
from extensions import db
from models import Course, Material


def seed_catalog():
    existing = {course.name: course for course in Course.query.all()}
    for english_name, hebrew_name in LEGACY_ENGLISH_NAMES.items():
        old = existing.get(english_name)
        if old is None:
            continue
        already = existing.get(hebrew_name)
        if already and already.id != old.id:
            Material.query.filter_by(course_id=old.id).update({"course_id": already.id})
            db.session.delete(old)
            existing.pop(english_name, None)
        else:
            old.name = hebrew_name
            existing[hebrew_name] = old
            existing.pop(english_name, None)
    db.session.commit()

    existing_names = {course.name for course in Course.query.all()}
    for name in COURSE_MAP.values():
        if name not in existing_names:
            db.session.add(Course(name=name))
            existing_names.add(name)
    db.session.commit()
