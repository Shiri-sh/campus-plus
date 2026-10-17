from extensions import db

# Hebrew-bearing columns. VARCHAR/TEXT on MSSQL use the database code page,
# which drops characters that SQLite stored as UTF-8.
_NON_UNICODE_TYPE_NAMES = frozenset({"VARCHAR", "CHAR", "TEXT", "STRING"})
# sys.foreign_keys.delete_referential_action: 2 means ON DELETE SET NULL.
_FK_SET_NULL = 2
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


def migration_statements(is_mssql, columns, unique_constraints=None):
    additions = _add_column_statements(is_mssql, columns)
    upgrades = _unicode_upgrade_statements(is_mssql, columns, unique_constraints)
    return additions + upgrades


def event_actor_fk_statements(constraint_name, delete_action):
    """Rebuild an existing actor foreign key so user deletes keep audit rows.

    A missing constraint, or one that already sets NULL, needs no change.
    Fresh databases get ON DELETE SET NULL from the model itself.
    """
    if not constraint_name or delete_action == _FK_SET_NULL:
        return []
    quoted = f"[{constraint_name}]"
    return [
        f"ALTER TABLE [event] DROP CONSTRAINT {quoted}",
        (
            f"ALTER TABLE [event] ADD CONSTRAINT {quoted} "
            "FOREIGN KEY (actor_id) REFERENCES [user] (id) ON DELETE SET NULL"
        ),
    ]


def _event_actor_fk():
    if not _is_mssql():
        return None, None
    row = db.session.execute(
        db.text(
            "SELECT fk.name, fk.delete_referential_action "
            "FROM sys.foreign_keys AS fk "
            "JOIN sys.foreign_key_columns AS fkc "
            "  ON fk.object_id = fkc.constraint_object_id "
            "JOIN sys.columns AS c "
            "  ON fkc.parent_object_id = c.object_id "
            " AND fkc.parent_column_id = c.column_id "
            "WHERE fk.parent_object_id = OBJECT_ID(N'event') "
            "  AND c.name = N'actor_id'"
        )
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


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
    statements = migration_statements(is_mssql, columns, unique_constraints)
    constraint_name, delete_action = _event_actor_fk()
    statements.extend(event_actor_fk_statements(constraint_name, delete_action))
    if not statements:
        return
    with db.engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
