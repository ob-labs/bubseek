"""OceanBase/seekdb runtime helpers and SQLAlchemy dialect patches."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, cast
from urllib.parse import urlparse

import pymysql
import pyobvector  # noqa: F401
import typer
from pydantic import ValidationError
from pyobvector.schema.dialect import OceanBaseDialect as _OceanBaseDialect
from sqlalchemy.dialects import registry

DEFAULT_MYSQL_PORT = 3306
MYSQL_DATABASE_NOT_FOUND_ERROR = 1049
MYSQL_SAVEPOINT_NOT_FOUND_ERROR = 1305
MYSQL_DUPLICATE_INDEX_ERROR = 1061

CREATE_DB_HINT = """
Please create the database manually, for example:
  mysql -h{host} -P{port} -u{user} -p -e "CREATE DATABASE `{database}` DEFAULT CHARACTER SET utf8mb4"

Or run: uv run python scripts/create-bub-db.py
"""


def normalize_oceanbase_url(url: str) -> str:
    """Treat MySQL-style seekdb URLs as OceanBase URLs."""
    normalized = url.strip()
    lowered = normalized.lower()
    if not lowered.startswith("mysql"):
        return normalized
    if lowered.startswith("mysql+oceanbase://"):
        return normalized
    if lowered.startswith("mysql+pymysql://"):
        return normalized.replace("mysql+pymysql://", "mysql+oceanbase://", 1)
    if lowered.startswith("mysql://"):
        return normalized.replace("mysql://", "mysql+oceanbase://", 1)
    return normalized


def resolve_tapestore_url(url: str | None = None) -> str:
    """Resolve the tapestore URL from an explicit value or the process environment."""
    if url is not None:
        return normalize_oceanbase_url(url)

    from bubseek.settings import load_bubseek_settings

    try:
        return load_bubseek_settings().tapestore_url
    except ValidationError:
        return ""


def mysql_connection_params(
    url: str | None = None,
) -> tuple[str, int, str, str, str] | None:
    """Return connection params for MySQL-compatible URLs."""
    resolved_url = resolve_tapestore_url(url)
    if not resolved_url:
        return None

    parsed = urlparse(resolved_url)
    backend_name = parsed.scheme.lower().split("+", 1)[0]
    if backend_name != "mysql":
        return None

    host = parsed.hostname or ""
    database = parsed.path.strip("/")
    if not host or not database:
        return None

    return (
        host,
        parsed.port or DEFAULT_MYSQL_PORT,
        parsed.username or "",
        parsed.password or "",
        database,
    )


def database_exists(host: str, port: int, user: str, password: str, database: str) -> bool:
    """Return whether the configured OceanBase or seekdb database already exists."""
    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
        )
        connection.close()
    except pymysql.err.OperationalError as exc:
        if exc.args[0] == MYSQL_DATABASE_NOT_FOUND_ERROR:
            return False
        raise
    return True


def create_database(host: str, port: int, user: str, password: str, database: str) -> bool:
    """Create the configured OceanBase or seekdb database when credentials permit."""
    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset="utf8mb4",
        )
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` DEFAULT CHARACTER SET utf8mb4")
        connection.close()
    except Exception:
        return False
    return True


def ensure_database(url: str | None = None) -> None:
    """Create the configured database on demand for MySQL-compatible backends."""
    params = mysql_connection_params(url)
    if params is None:
        return

    host, port, user, password, database = params
    try:
        if database_exists(host, port, user, password, database):
            return
    except Exception as exc:
        typer.echo(f"Cannot connect to {host}:{port}: {exc}", err=True)
        typer.echo("Ensure OceanBase/seekdb is running.", err=True)
        raise typer.Exit(1) from exc

    hint = CREATE_DB_HINT.format(host=host, port=port, user=user, database=database).strip()
    if sys.stdin.isatty() and not typer.confirm(
        f"Database {database!r} does not exist. Create it?",
        default=False,
    ):
        typer.echo(hint, err=True)
        raise typer.Exit(1)

    if create_database(host, port, user, password, database):
        typer.echo(f"Database {database!r} created at {host}:{port}", err=True)
        return

    typer.echo(f"Cannot create database {database!r}.", err=True)
    typer.echo(hint, err=True)
    raise typer.Exit(1)


def _is_savepoint_not_exist(exc: BaseException) -> bool:
    """Check if exception is MySQL 1305 (savepoint does not exist)."""
    if isinstance(exc, pymysql.err.OperationalError) and exc.args and exc.args[0] == MYSQL_SAVEPOINT_NOT_FOUND_ERROR:
        return True
    original = getattr(exc, "orig", None)
    if original is not None and original is not exc:
        return _is_savepoint_not_exist(original)
    return False


class OceanBaseDialect(_OceanBaseDialect):
    """OceanBase dialect that tolerates missing savepoints."""

    supports_statement_cache = True

    def do_release_savepoint(self, connection, name: str) -> None:
        try:
            super().do_release_savepoint(connection, name)
        except Exception as exc:
            if not _is_savepoint_not_exist(exc):
                raise

    def do_rollback_to_savepoint(self, connection, name: str) -> None:
        try:
            super().do_rollback_to_savepoint(connection, name)
        except Exception as exc:
            if not _is_savepoint_not_exist(exc):
                raise


registry.register("mysql.oceanbase", "bubseek.oceanbase", "OceanBaseDialect")


def _patch_tape_store_validate_schema() -> None:
    """Tolerate duplicate index creation during tapestore schema validation."""
    try:
        from bub_tapestore_sqlalchemy import store as _store
    except ImportError:
        return

    store_cls = _store.SQLAlchemyTapeStore
    original_validate = cast(Callable[[Any], None], store_cls._validate_schema)

    def _validate_schema_tolerant(self: Any) -> None:
        try:
            original_validate(self)
        except Exception as exc:
            original_exc = getattr(exc, "orig", exc)
            if getattr(original_exc, "args", (None,))[0] == MYSQL_DUPLICATE_INDEX_ERROR:
                return
            if "Duplicate key name" in str(exc):
                return
            raise

    cast(Any, store_cls)._validate_schema = _validate_schema_tolerant


_patch_tape_store_validate_schema()
