from extensions import db

# Hebrew-bearing columns. VARCHAR/TEXT on MSSQL use the database code page,
# which drops characters that SQLite stored as UTF-8.
_NON_UNICODE_TYPE_NAMES = frozenset({"VARCHAR", "CHAR", "TEXT", "STRING"})
_NVARCHAR_COLUMNS = {
    ("material", "file_name"): "NVARCHAR(255) NOT NULL",
    ("material", "lecturer"): "NVARCHAR(255) NULL",
    ("material", "ai_summary"): "NVARCHAR(MAX) NULL",
    ("report", "message"): "NVARCHAR(MAX) NOT NULL",
    ("report", "admin_reply"): "NVARCHAR(MAX) NULL",
}


def _is_mssql():
    return db.engine.dialect.name == "mssql"


def _column_types(table):
    inspector = db.inspect(db.engine)
    return {
        column["name"]: type(column["type"]).__name__.upper()
        for column in inspector.get_columns(table)
    }


def _quote(table, is_mssql):
    if is_mssql:
        return f"[{table}]"
    return table


def _add_column_statements(is_mssql, columns):
    bool_type = "BIT" if is_mssql else "BOOLEAN"
    text_type = "NVARCHAR(MAX)" if is_mssql else "TEXT"
    user = _quote("user", is_mssql)
    material = _quote("material", is_mssql)
    report = _quote("report", is_mssql)
    statements = []

    user_cols = columns["user"]
    if "is_blocked" not in user_cols:
        statements.append(f"ALTER TABLE {user} ADD is_blocked {bool_type} DEFAULT 0")
    if "last_login_at" not in user_cols:
        statements.append(f"ALTER TABLE {user} ADD last_login_at DATETIME")

    material_cols = columns["material"]
    if "confidence" not in material_cols:
        statements.append(f"ALTER TABLE {material} ADD confidence INTEGER")
    if "ai_recommendation" not in material_cols:
        statements.append(f"ALTER TABLE {material} ADD ai_recommendation VARCHAR(20)")

    report_cols = columns["report"]
    if "admin_reply" not in report_cols:
        statements.append(f"ALTER TABLE {report} ADD admin_reply {text_type}")
    if "replied_at" not in report_cols:
        statements.append(f"ALTER TABLE {report} ADD replied_at DATETIME")
    return statements


def _unicode_upgrade_statements(is_mssql, columns):
    if not is_mssql:
        return []

    statements = []
    for (table, column), declaration in _NVARCHAR_COLUMNS.items():
        existing = columns[table].get(column)
        if existing is None or existing.upper() not in _NON_UNICODE_TYPE_NAMES:
            continue
        quoted = _quote(table, True)
        statements.append(f"ALTER TABLE {quoted} ALTER COLUMN {column} {declaration}")
    return statements


def migration_statements(is_mssql, columns):
    additions = _add_column_statements(is_mssql, columns)
    upgrades = _unicode_upgrade_statements(is_mssql, columns)
    return additions + upgrades


def ensure_schema():
    columns = {
        "user": _column_types("user"),
        "material": _column_types("material"),
        "report": _column_types("report"),
    }
    statements = migration_statements(_is_mssql(), columns)
    if not statements:
        return
    with db.engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
