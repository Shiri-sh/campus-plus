from courses import COURSE_MAP
from extensions import db
from models import Course, Material

# Old English names → new Hebrew names (for migration from English to Hebrew)
_ENGLISH_TO_HEBREW = {
    "Automata and Formal Languages": "אוטומטים ושפות פורמליות",
    "Information Retrieval": "אחזור מידע",
    "Calculus 1": "אינפי א'",
    "Calculus 2": "אינפי ב'",
    "Linear Algebra 1": "אלגברה ליניארית א'",
    "Linear Algebra 2": "אלגברה ליניארית ב'",
    "Analog and Digital Electronics": "אלקטרוניקה אנלוגית וספרתית",
    "English for Computer Science": "אנגלית למדעי המחשב",
    "Databases": "בסיסי נתונים",
    "Library Resources": "הכרת משאבי הספריה",
    "Software Engineering": "הנדסת תוכנה",
    "Probability": "הסתברות",
    "Computability and Complexity": "חישוביות ומורכבות החישובים",
    "Data Mining": "כריית מידע",
    "Mathematical Logic": "לוגיקה מתמטית",
    "Introduction to Information Security": "מבוא לאבטחת מידע",
    "Introduction to Artificial Intelligence": "מבוא לבינה מלאכותית",
    "Introduction to Software Engineering": "מבוא להנדסת תוכנה",
    "Introduction to Computer Science": "מבוא למדעי המחשב",
    "Introduction to Reverse Engineering": "מבוא לרברסינג",
    "Introduction to Computer Networks": "מבוא לתקשורת מחשבים",
    "Exams Archive": "מבחנים",
    "Computer Architecture": "מבנה המחשב",
    "Data Structures 2": "מבנה נתונים ב'",
    "Data Structures and Programs 1": "מבנה נתונים ותוכניות א'",
    "Structure of Programming Languages": "מבנה שפות תכנות",
    "Mini Project in Databases": "מיני פרויקט בבסיסי נתונים",
    "Mini Project in Windows Systems": "מיני פרויקט במערכות חלונות",
    "Computer Architecture Lab": "מעבדה במבנה המחשב",
    "Operating Systems": "מערכות הפעלה",
    "Real-Time Systems and Parallel Programming": "מערכות זמן אמת ותכנות מקבילי",
    "Digital Systems (Logic)": "מערכות ספרתיות (לוגיקה)",
    "Differential Equations": "משוואות דיפרנציאליות",
    "Discrete Mathematics": "מתמטיקה בדידה",
    "Algorithms and Complexity Analysis": "ניתוח אלגוריתמים וסיבוכיות",
    "Computerized Systems Analysis": "ניתוח מערכות ממוחשבות",
    "Statistics": "סטטיסטיקה",
    "Object-Oriented Design and Programming for Engineering": "עיצוב ותכנות מונחה עצמים",
    "Principles of Programming Languages": "עקרונות שפות תוכנה",
    "Physics": "פיזיקה",
    "Precalculus": "קדם במתמטיקה",
    "Compilers": "קומפיילרים",
    "Elective Courses": "קורסי רשות",
    "TCP/IP Networks": "רשתות TCP/IP",
    "Software Design": "תכנון תוכנה",
    "Advanced Object-Oriented Programming": "תכנות מונחה עצמים מתקדם",
    "Functional and Logic Programming": "תכנות פונקציונלי ולוגי",
}


def _migrate_english_courses():
    """Rename courses from English to Hebrew, merging duplicates.

    Each pair is committed individually to avoid unique-constraint
    conflicts when multiple renames run in a single flush.
    """
    for english, hebrew in _ENGLISH_TO_HEBREW.items():
        old = Course.query.filter_by(name=english).first()
        if old is None:
            continue
        target = Course.query.filter_by(name=hebrew).first()
        if target:
            Material.query.filter_by(course_id=old.id).update(
                {"course_id": target.id}
            )
            db.session.delete(old)
        else:
            old.name = hebrew
        db.session.commit()


def seed_catalog():
    _migrate_english_courses()
    existing = {course.name for course in Course.query.all()}
    for name in COURSE_MAP.values():
        if name not in existing:
            db.session.add(Course(name=name))
            existing.add(name)
    db.session.commit()
