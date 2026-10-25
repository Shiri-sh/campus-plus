import pytest
from flask import Flask
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from extensions import db
from schema import ensure_schema, migration_statements


def complete_columns():
    return {
        "user": {
            "is_blocked": "BOOLEAN",
            "last_login_at": "DATETIME",
        },
        "course": {
            "name": "NVARCHAR",
        },
        "material": {
            "confidence": "INTEGER",
            "ai_recommendation": "VARCHAR",
            "file_name": "NVARCHAR",
            "lecturer": "NVARCHAR",
            "ai_summary": "NVARCHAR",
        },
        "report": {
            "admin_reply": "NVARCHAR",
            "replied_at": "DATETIME",
            "message": "NVARCHAR",
        },
    }


def without_column(table, column):
    columns = complete_columns()
    del columns[table][column]
    return columns


def columns_with(table, column, type_name):
    columns = complete_columns()
    columns[table][column] = type_name
    return columns


@pytest.mark.parametrize(
    ("table", "column", "is_mssql", "expected"),
    [
        (
            "user",
            "is_blocked",
            False,
            "ALTER TABLE user ADD is_blocked BOOLEAN DEFAULT 0",
        ),
        (
            "user",
            "is_blocked",
            True,
            "ALTER TABLE [user] ADD is_blocked BIT DEFAULT 0",
        ),
        (
            "user",
            "last_login_at",
            False,
            "ALTER TABLE user ADD last_login_at DATETIME",
        ),
        (
            "user",
            "last_login_at",
            True,
            "ALTER TABLE [user] ADD last_login_at DATETIME",
        ),
        (
            "material",
            "confidence",
            False,
            "ALTER TABLE material ADD confidence INTEGER",
        ),
        (
            "material",
            "confidence",
            True,
            "ALTER TABLE [material] ADD confidence INTEGER",
        ),
        (
            "material",
            "ai_recommendation",
            False,
            "ALTER TABLE material ADD ai_recommendation VARCHAR(20)",
        ),
        (
            "material",
            "ai_recommendation",
            True,
            "ALTER TABLE [material] ADD ai_recommendation VARCHAR(20)",
        ),
        (
            "report",
            "admin_reply",
            False,
            "ALTER TABLE report ADD admin_reply TEXT",
        ),
        (
            "report",
            "admin_reply",
            True,
            "ALTER TABLE [report] ADD admin_reply NVARCHAR(MAX)",
        ),
        (
            "report",
            "replied_at",
            False,
            "ALTER TABLE report ADD replied_at DATETIME",
        ),
        (
            "report",
            "replied_at",
            True,
            "ALTER TABLE [report] ADD replied_at DATETIME",
        ),
    ],
)
def test_missing_column_statement(table, column, is_mssql, expected):
    columns = without_column(table, column)

    statements = migration_statements(is_mssql, columns)

    assert statements == [expected]


@pytest.mark.parametrize(
    ("table", "column", "type_name", "expected"),
    [
        (
            "material",
            "file_name",
            "VARCHAR",
            "ALTER TABLE [material] ALTER COLUMN file_name NVARCHAR(255) NOT NULL",
        ),
        (
            "material",
            "lecturer",
            "VARCHAR",
            "ALTER TABLE [material] ALTER COLUMN lecturer NVARCHAR(255) NULL",
        ),
        (
            "material",
            "ai_summary",
            "VARCHAR",
            "ALTER TABLE [material] ALTER COLUMN ai_summary NVARCHAR(MAX) NULL",
        ),
        (
            "material",
            "ai_summary",
            "TEXT",
            "ALTER TABLE [material] ALTER COLUMN ai_summary NVARCHAR(MAX) NULL",
        ),
        (
            "report",
            "message",
            "VARCHAR",
            "ALTER TABLE [report] ALTER COLUMN message NVARCHAR(MAX) NOT NULL",
        ),
        (
            "report",
            "admin_reply",
            "TEXT",
            "ALTER TABLE [report] ALTER COLUMN admin_reply NVARCHAR(MAX) NULL",
        ),
        (
            "report",
            "admin_reply",
            "STRING",
            "ALTER TABLE [report] ALTER COLUMN admin_reply NVARCHAR(MAX) NULL",
        ),
    ],
)
def test_upgrades_non_unicode_column_on_mssql(table, column, type_name, expected):
    columns = columns_with(table, column, type_name)

    statements = migration_statements(True, columns)

    assert statements == [expected]


@pytest.mark.parametrize("is_mssql", [False, True])
def test_complete_schema_needs_no_statements(is_mssql):
    statements = migration_statements(is_mssql, complete_columns())

    assert statements == []


def test_drops_event_actor_foreign_key_on_mssql():
    statements = migration_statements(
        True,
        complete_columns(),
        event_foreign_keys=[
            {
                "name": "FK_event_actor_id_user",
                "constrained_columns": ["actor_id"],
                "referred_table": "user",
            }
        ],
    )

    assert statements == ["ALTER TABLE [event] DROP CONSTRAINT [FK_event_actor_id_user]"]


def test_sqlite_does_not_emit_a_drop_constraint_for_event_actor():
    statements = migration_statements(
        False,
        complete_columns(),
        event_foreign_keys=[
            {
                "name": "fk_event_actor_id",
                "constrained_columns": ["actor_id"],
                "referred_table": "user",
            }
        ],
    )

    assert statements == []


def test_sqlite_does_not_rewrite_varchar_file_name():
    columns = columns_with("material", "file_name", "VARCHAR")

    statements = migration_statements(False, columns)

    assert statements == []


def test_ensure_schema_adds_missing_column_on_sqlite():
    app = Flask("ensure-schema-sqlite")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    db.init_app(app)

    with app.app_context():
        db.metadata.create_all(db.engine)
        with db.engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE user DROP COLUMN is_blocked")
        ensure_schema()
        with db.engine.connect() as connection:
            rows = connection.exec_driver_sql("SELECT is_blocked FROM user").fetchall()

    assert rows == []
