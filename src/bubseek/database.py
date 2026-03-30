"""Database bootstrap helpers for SeekDB/OceanBase-backed runtimes."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from bubseek.config import BubSeekSettings

CREATE_DB_HINT = """
Please create the database manually, for example:
  mysql -h{host} -P{port} -u{user} -p -e "CREATE DATABASE `{database}` DEFAULT CHARACTER SET utf8mb4"

Or run: uv run python scripts/create-bub-db.py
"""


def database_exists(host: str, port: int, user: str, password: str, database: str) -> bool:
    """Return whether the configured OceanBase or SeekDB database already exists."""
    import pymysql

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
        )
        conn.close()
    except pymysql.err.OperationalError as exc:
        if exc.args[0] == 1049:
            return False
        raise
    else:
        return True


def create_database(host: str, port: int, user: str, password: str, database: str) -> bool:
    """Create the configured OceanBase or SeekDB database when credentials permit."""
    import pymysql

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset="utf8mb4",
        )
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` DEFAULT CHARACTER SET utf8mb4")
        conn.close()
    except Exception:
        return False
    else:
        return True


def ensure_database(workspace: Path | None = None) -> None:
    """Pre-flight database creation for MySQL-compatible backends only."""
    settings = BubSeekSettings.from_workspace((workspace or Path.cwd()).resolve())
    params = settings.db.mysql_connection_params()
    if params is None:
        return

    host, port, user, password, database = params
    try:
        if database_exists(host, port, user, password, database):
            return
    except Exception as exc:
        typer.echo(f"Cannot connect to {host}:{port}: {exc}", err=True)
        typer.echo("Ensure OceanBase/SeekDB is running.", err=True)
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
