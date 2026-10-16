import pytest

from db_config import IncompleteDatabaseConfig, resolve_database_url

INSTANCE_PATH = "/tmp/campus-instance"
SQLITE_URL = "sqlite:////tmp/campus-instance/campus_plus.db"
MSSQL_ENV = {
    "DB_SERVER": "sql.example",
    "DB_NAME": "campus",
    "DB_USER": "student",
    "DB_PASSWORD": "secret",
}


def test_database_url_overrides_db_env():
    environ = dict(MSSQL_ENV)
    environ["DATABASE_URL"] = "mssql+pymssql://explicit@host/db"

    url = resolve_database_url(environ, INSTANCE_PATH)

    assert url == "mssql+pymssql://explicit@host/db"


@pytest.mark.parametrize(
    ("user", "password", "expected"),
    [
        (
            "student",
            "secret",
            "mssql+pymssql://student:secret@sql.example/campus",
        ),
        (
            "user@domain",
            "p@ss/word",
            "mssql+pymssql://user%40domain:p%40ss%2Fword@sql.example/campus",
        ),
    ],
)
def test_builds_mssql_url_from_db_env(user, password, expected):
    environ = {
        "DB_SERVER": "sql.example",
        "DB_NAME": "campus",
        "DB_USER": user,
        "DB_PASSWORD": password,
    }

    url = resolve_database_url(environ, INSTANCE_PATH)

    assert url == expected


@pytest.mark.parametrize(
    "missing_key",
    ["DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD"],
)
def test_partial_db_env_names_the_missing_key(missing_key):
    environ = dict(MSSQL_ENV)
    del environ[missing_key]

    with pytest.raises(IncompleteDatabaseConfig) as caught:
        resolve_database_url(environ, INSTANCE_PATH)

    assert caught.value.missing == (missing_key,)


def test_partial_db_env_reports_every_missing_key():
    environ = {"DB_SERVER": "sql.example", "DB_USER": "student"}

    with pytest.raises(IncompleteDatabaseConfig) as caught:
        resolve_database_url(environ, INSTANCE_PATH)

    assert caught.value.missing == ("DB_NAME", "DB_PASSWORD")


@pytest.mark.parametrize("password", ["", None])
def test_blank_password_is_incomplete(password):
    environ = dict(MSSQL_ENV)
    environ["DB_PASSWORD"] = password

    with pytest.raises(IncompleteDatabaseConfig) as caught:
        resolve_database_url(environ, INSTANCE_PATH)

    assert caught.value.missing == ("DB_PASSWORD",)


def test_empty_environ_uses_sqlite():
    url = resolve_database_url({}, INSTANCE_PATH)

    assert url == SQLITE_URL


def test_empty_database_url_with_db_env_uses_mssql():
    environ = dict(MSSQL_ENV)
    environ["DATABASE_URL"] = ""

    url = resolve_database_url(environ, INSTANCE_PATH)

    assert url == "mssql+pymssql://student:secret@sql.example/campus"


def test_ignores_process_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mssql+pymssql://leaked@host/db")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    url = resolve_database_url({}, INSTANCE_PATH)

    assert url == SQLITE_URL
