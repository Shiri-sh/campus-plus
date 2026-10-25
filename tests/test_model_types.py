import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects.mssql.pymssql import MSDialect_pymssql

import models  # noqa: F401
from extensions import db


def somee_dialect():
    dialect = MSDialect_pymssql()
    dialect.deprecate_large_types = True
    dialect.server_version_info = (15, 0, 2000, 5)
    return dialect


def column_names(engine, table):
    return {column["name"] for column in inspect(engine).get_columns(table)}


def compiled_type(table_name, column_name, dialect):
    column = db.metadata.tables[table_name].c[column_name]
    return column.type.compile(dialect=dialect)


@pytest.mark.parametrize(
    ("table_name", "column_name", "expected"),
    [
        ("material", "file_name", "NVARCHAR(255)"),
        ("material", "lecturer", "NVARCHAR(255)"),
        ("material", "ai_summary", "NVARCHAR(max)"),
        ("report", "message", "NVARCHAR(max)"),
        ("report", "admin_reply", "NVARCHAR(max)"),
        ("event", "payload", "NVARCHAR(max)"),
    ],
)
def test_hebrew_columns_use_national_types_on_mssql(table_name, column_name, expected):
    dialect = somee_dialect()

    compiled = compiled_type(table_name, column_name, dialect)

    assert compiled == expected


@pytest.mark.parametrize(
    ("table_name", "column_name", "expected"),
    [
        ("user", "email", "VARCHAR(255)"),
        ("course", "name", "VARCHAR(255)"),
        ("material", "ai_recommendation", "VARCHAR(20)"),
        ("material", "file_path", "VARCHAR(500)"),
    ],
)
def test_ascii_columns_stay_varchar_on_mssql(table_name, column_name, expected):
    dialect = somee_dialect()

    compiled = compiled_type(table_name, column_name, dialect)

    assert compiled == expected


def test_sqlite_file_name_keeps_local_text_type():
    dialect = create_engine("sqlite://").dialect

    compiled = compiled_type("material", "file_name", dialect)

    assert compiled == "VARCHAR(255)"


def test_sqlite_create_all_creates_material_file_name():
    engine = create_engine("sqlite://")

    db.metadata.create_all(engine)

    assert "file_name" in column_names(engine, "material")


def test_sqlite_create_all_creates_event_columns():
    engine = create_engine("sqlite://")

    db.metadata.create_all(engine)

    assert column_names(engine, "event") == {
        "id",
        "event_type",
        "entity_type",
        "entity_id",
        "actor_id",
        "payload",
        "created_at",
    }


def test_event_actor_id_has_no_foreign_key():
    assert db.metadata.tables["event"].c.actor_id.foreign_keys == set()
