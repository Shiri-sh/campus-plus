from extensions import db

# Hebrew-bearing columns. VARCHAR/TEXT on MSSQL use the database code page,
# which drops characters that SQLite stored as UTF-8.
_NON_UNICODE_TYPE_NAMES = frozenset({"VARCHAR", "CHAR", "TEXT", "STRING"})
_NVARCHAR_COLUMNS = {
    ("course", "name"): "NVARCHAR(255) NOT NULL",
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


def _unique_constraints_for(table):
    inspector = db.inspect(db.engine)
    try:
        return inspector.get_unique_constraints(table)
    except NotImplementedError:
        pass
    # pymssql dialect doesn't implement get_unique_constraints;
    # fall back to querying MSSQL system tables directly.
    rows = db.session.execute(
        db.text(
            "SELECT kc.name, c.name "
            "FROM sys.key_constraints kc "
            "JOIN sys.index_columns ic "
            "  ON kc.parent_object_id = ic.object_id "
            "  AND kc.unique_index_id = ic.index_id "
            "JOIN sys.columns c "
            "  ON ic.object_id = c.object_id "
            "  AND ic.column_id = c.column_id "
            "WHERE kc.type = 'UQ' "
            "  AND kc.parent_object_id = OBJECT_ID(:table)"
        ),
        {"table": table},
    ).fetchall()
    grouped = {}
    for constraint_name, column_name in rows:
        grouped.setdefault(constraint_name, []).append(column_name)
    return [
        {"name": name, "column_names": cols}
        for name, cols in grouped.items()
    ]


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
    if is_mssql and "file_type" in material_cols:
        statements.append(f"ALTER TABLE {material} DROP COLUMN file_type")
    return statements


def _unicode_upgrade_statements(is_mssql, columns, unique_constraints=None):
    """Generate ALTER COLUMN statements for VARCHAR→NVARCHAR upgrades.

    ``unique_constraints`` is a dict mapping table names to their
    constraint lists (from ``inspector.get_unique_constraints``).
    When ``None``, constraint drop/re-add is skipped (safe for unit tests).
    """
    if not is_mssql:
        return []

    statements = []
    for (table, column), declaration in _NVARCHAR_COLUMNS.items():
        existing = columns[table].get(column)
        if existing is None or existing.upper() not in _NON_UNICODE_TYPE_NAMES:
            continue
        quoted = _quote(table, True)
        constraints = (unique_constraints or {}).get(table, [])
        for constraint in constraints:
            if column in constraint["column_names"]:
                statements.append(
                    f"ALTER TABLE {quoted} DROP CONSTRAINT [{constraint['name']}]"
                )
        statements.append(f"ALTER TABLE {quoted} ALTER COLUMN {column} {declaration}")
        for constraint in constraints:
            if column in constraint["column_names"]:
                cols = ", ".join(constraint["column_names"])
                statements.append(
                    f"ALTER TABLE {quoted} ADD CONSTRAINT [{constraint['name']}] UNIQUE ({cols})"
                )
    return statements


def _drop_event_actor_fk_statements(is_mssql, event_foreign_keys):
    """Drop event.actor_id → user.id so a deleted account can leave the audit row.

    SQLite does not support DROP CONSTRAINT. Local SQLite also leaves foreign
    keys off, so only MSSQL (somee.com) needs the statement. Existing event
    rows stay; this does not rebuild or delete the table.
    """
    if not is_mssql:
        return []
    statements = []
    for constraint in event_foreign_keys or []:
        columns = [name.lower() for name in constraint.get("constrained_columns") or []]
        referred = (constraint.get("referred_table") or "").lower()
        name = constraint.get("name")
        if "actor_id" in columns and referred == "user" and name:
            statements.append(f"ALTER TABLE [event] DROP CONSTRAINT [{name}]")
    return statements


def migration_statements(
    is_mssql,
    columns,
    unique_constraints=None,
    event_foreign_keys=None,
):
    additions = _add_column_statements(is_mssql, columns)
    upgrades = _unicode_upgrade_statements(is_mssql, columns, unique_constraints)
    drops = _drop_event_actor_fk_statements(is_mssql, event_foreign_keys)
    return additions + upgrades + drops


def _event_foreign_keys():
    inspector = db.inspect(db.engine)
    if not inspector.has_table("event"):
        return []
    return inspector.get_foreign_keys("event")


def ensure_schema():
    is_mssql = _is_mssql()
    columns = {
        "user": _column_types("user"),
        "course": _column_types("course"),
        "material": _column_types("material"),
        "report": _column_types("report"),
    }
    unique_constraints = {}
    if is_mssql:
        for table in columns:
            unique_constraints[table] = _unique_constraints_for(table)
    statements = migration_statements(
        is_mssql,
        columns,
        unique_constraints,
        _event_foreign_keys(),
    )
    if not statements:
        return
    with db.engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
