"""Single entry bootstrap for forwarding bubseek invocations to Bub."""

from __future__ import annotations

import errno
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import typer

from bubseek.config import BubSeekSettings, env_with_workspace_dotenv

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


def _resolve_workspace(args: list[str], default_workspace: Path) -> Path:
    for index, arg in enumerate(args):
        if arg in {"--workspace", "-w"} and index + 1 < len(args):
            return Path(args[index + 1]).expanduser().resolve()
        if arg.startswith("--workspace="):
            return Path(arg.split("=", 1)[1]).expanduser().resolve()
    return default_workspace.resolve()


def _should_ensure_database(args: list[str]) -> bool:
    """Skip DB preflight for pure help/version flows."""
    if not args:
        return False
    return not any(arg in {"--help", "-h", "help", "--version"} for arg in args)


@dataclass(slots=True)
class BubSeekBootstrap:
    """Bootstrap runtime state for a single bubseek invocation."""

    workspace: Path
    settings: BubSeekSettings

    @classmethod
    def from_workspace(cls, workspace: Path | None = None) -> BubSeekBootstrap:
        resolved_workspace = (workspace or Path.cwd()).resolve()
        return cls(
            workspace=resolved_workspace,
            settings=BubSeekSettings.from_workspace(resolved_workspace),
        )

    def ensure_database(self) -> None:
        """Pre-flight database creation for MySQL-compatible backends only."""
        params = self.settings.db.mysql_connection_params()
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

    def forwarded_environment(self, args: list[str]) -> dict[str, str]:
        """Merge workspace .env and defaults into the Bub subprocess environment."""
        env = env_with_workspace_dotenv(self.workspace)
        settings = BubSeekSettings.from_workspace(self.workspace)
        env.setdefault("BUB_TAPESTORE_SQLALCHEMY_URL", settings.db.resolved_tapestore_url)
        env.setdefault("BUB_WORKSPACE_PATH", str(_resolve_workspace(args, self.workspace)))
        return env

    def run(self, args: list[str]) -> None:
        """Replace the current process with Bub after preparing runtime defaults."""
        if _should_ensure_database(args):
            self.ensure_database()

        executable = shutil.which("bub")
        if executable is None:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), "bub")

        env = self.forwarded_environment(args)
        command = [executable, *(args or ["--help"])]
        try:
            os.execve(executable, command, env)  # noqa: S606
        except OSError as exc:
            sys.exit(exc.errno if exc.errno else 1)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `bubseek` console script."""
    args = list(sys.argv[1:] if argv is None else argv)
    workspace = _resolve_workspace(args, Path.cwd())
    BubSeekBootstrap.from_workspace(workspace).run(args)
    return 0
