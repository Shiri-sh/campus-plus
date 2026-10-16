from extensions import db


def _columns(table):
    inspector = db.inspect(db.engine)
    return {column["name"] for column in inspector.get_columns(table)}


def _is_mssql():
    return db.engine.dialect.name == "mssql"


def ensure_schema():
    is_mssql = _is_mssql()

    def quote(table):
        return f"[{table}]" if is_mssql else table

    def bool_type():
        return "BIT" if is_mssql else "BOOLEAN"

    additions = []

    user_cols = _columns("user")
    user_t = quote("user")
    if "is_blocked" not in user_cols:
        additions.append(
            f"ALTER TABLE {user_t} ADD is_blocked {bool_type()} DEFAULT 0"
        )
    if "last_login_at" not in user_cols:
        additions.append(f"ALTER TABLE {user_t} ADD last_login_at DATETIME")

    material_cols = _columns("material")
    material_t = quote("material")
    if "confidence" not in material_cols:
        additions.append(f"ALTER TABLE {material_t} ADD confidence INTEGER")
    if "ai_recommendation" not in material_cols:
        additions.append(
            f"ALTER TABLE {material_t} ADD ai_recommendation VARCHAR(20)"
        )

    report_cols = _columns("report")
    report_t = quote("report")
    if "admin_reply" not in report_cols:
        additions.append(f"ALTER TABLE {report_t} ADD admin_reply {'NVARCHAR(MAX)' if is_mssql else 'TEXT'}")
    if "replied_at" not in report_cols:
        additions.append(f"ALTER TABLE {report_t} ADD replied_at DATETIME")

    if not additions:
        return
    with db.engine.begin() as connection:
        for statement in additions:
            connection.exec_driver_sql(statement)
