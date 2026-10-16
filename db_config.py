import os
from urllib.parse import quote_plus

DB_ENV_KEYS = ("DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD")
SQLITE_FILENAME = "campus_plus.db"


class IncompleteDatabaseConfig(ValueError):
    def __init__(self, missing):
        self.missing = tuple(missing)
        missing_list = ", ".join(self.missing)
        super().__init__(
            "Database configuration is incomplete. "
            "Set DATABASE_URL, or set all of "
            "DB_SERVER, DB_NAME, DB_USER, and DB_PASSWORD. "
            f"Missing: {missing_list}"
        )


def _db_values(environ):
    values = {}
    missing = []
    for key in DB_ENV_KEYS:
        value = environ.get(key) or ""
        if value:
            values[key] = value
        else:
            missing.append(key)
    return values, tuple(missing)


def _mssql_url(values):
    user = quote_plus(values["DB_USER"])
    password = quote_plus(values["DB_PASSWORD"])
    return (
        f"mssql+pymssql://{user}:{password}"
        f"@{values['DB_SERVER']}/{values['DB_NAME']}"
    )


def _sqlite_url(instance_path):
    return "sqlite:///" + os.path.join(instance_path, SQLITE_FILENAME)


def resolve_database_url(environ, instance_path):
    """Pick a SQLAlchemy URL without opening a connection.

    DATABASE_URL wins. All four DB_* variables build an MSSQL URL.
    None of those falls back to SQLite. A partial DB_* set raises.
    """
    database_url = environ.get("DATABASE_URL") or ""
    if database_url:
        return database_url

    values, missing = _db_values(environ)
    if values and missing:
        raise IncompleteDatabaseConfig(missing)
    if values:
        return _mssql_url(values)
    return _sqlite_url(instance_path)
