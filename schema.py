from extensions import db


def _columns(table):
    inspector = db.inspect(db.engine)
    return {column["name"] for column in inspector.get_columns(table)}


def ensure_schema():
    additions = []
    user_cols = _columns("user")
    if "is_blocked" not in user_cols:
        additions.append("ALTER TABLE user ADD COLUMN is_blocked BOOLEAN DEFAULT 0")
    if "last_login_at" not in user_cols:
        additions.append("ALTER TABLE user ADD COLUMN last_login_at DATETIME")

    material_cols = _columns("material")
    if "confidence" not in material_cols:
        additions.append("ALTER TABLE material ADD COLUMN confidence INTEGER")
    if "ai_recommendation" not in material_cols:
        additions.append("ALTER TABLE material ADD COLUMN ai_recommendation VARCHAR(20)")

    report_cols = _columns("report")
    if "admin_reply" not in report_cols:
        additions.append("ALTER TABLE report ADD COLUMN admin_reply TEXT")
    if "replied_at" not in report_cols:
        additions.append("ALTER TABLE report ADD COLUMN replied_at DATETIME")

    if not additions:
        return
    with db.engine.begin() as connection:
        for statement in additions:
            connection.exec_driver_sql(statement)
