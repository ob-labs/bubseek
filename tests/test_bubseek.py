from __future__ import annotations

import importlib
import sys
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from bub.skills import _read_skill

REPO_ROOT = Path(__file__).resolve().parents[1]
BUBSEEK_SRC = REPO_ROOT / "src"


@contextmanager
def imported_bubseek_modules(*module_names: str) -> Iterator[list[ModuleType]]:
    sys.path.insert(0, str(BUBSEEK_SRC))
    try:
        yield [importlib.import_module(name) for name in module_names]
    finally:
        sys.path.remove(str(BUBSEEK_SRC))
        for module_name in list(sys.modules):
            if module_name == "bubseek" or module_name.startswith("bubseek."):
                sys.modules.pop(module_name, None)


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _settings_with_db_params(params: tuple[str, int, str, str, str] | None) -> SimpleNamespace:
    db = SimpleNamespace(mysql_connection_params=lambda: params)
    return SimpleNamespace(db=db)


def test_distribution_metadata_exposes_bub_plugin_without_console_script() -> None:
    data = _load_pyproject()

    project = data["project"]
    assert "scripts" not in project
    assert project["entry-points"]["bub"] == {
        "oceanbase-dialect": "bubseek.oceanbase:register",
    }


def test_pyproject_includes_package_and_builtin_skills_in_wheel() -> None:
    data = _load_pyproject()

    build = data["tool"]["pdm"]["build"]
    assert build["includes"] == [
        "src/bubseek",
        "src/skills",
    ]
    assert build["skills"]


def test_bundled_skills_have_valid_frontmatter() -> None:
    skill_root = REPO_ROOT / "src" / "skills"
    skill_names = []

    for skill_dir in sorted(path for path in skill_root.iterdir() if path.is_dir()):
        metadata = _read_skill(skill_dir, source="builtin")
        assert metadata is not None
        skill_names.append(metadata.name)

    assert "github-repo-cards" in skill_names


def test_resolve_tapestore_url_requires_explicit_url(monkeypatch, tmp_path: Path) -> None:
    with imported_bubseek_modules("bubseek.config") as [config_mod]:
        monkeypatch.setenv("BUB_HOME", str(tmp_path / "runtime-home"))
        monkeypatch.delenv("BUB_WORKSPACE_PATH", raising=False)
        monkeypatch.setenv("BUB_TAPESTORE_SQLALCHEMY_URL", "")

        settings = config_mod.DatabaseSettings()

    assert settings.resolved_tapestore_url == ""
    assert settings.backend_name == ""
    assert settings.mysql_connection_params() is None


def test_database_settings_extract_mysql_params(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.config") as [config_mod]:
        monkeypatch.setenv(
            "BUB_TAPESTORE_SQLALCHEMY_URL",
            "mysql+oceanbase://seek:secret@seekdb.example:2881/analytics",
        )

        settings = config_mod.DatabaseSettings()

    assert settings.backend_name == "mysql"
    assert settings.mysql_connection_params() == (
        "seekdb.example",
        2881,
        "seek",
        "secret",
        "analytics",
    )


def test_resolve_tapestore_url_reads_workspace_env_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text(
        "BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://workspace:secret@seekdb.example:2881/workspace_db\n",
        encoding="utf-8",
    )

    with imported_bubseek_modules("bubseek.config") as [config_mod]:
        url = config_mod.resolve_tapestore_url(workspace=workspace)

    assert url == "mysql+oceanbase://workspace:secret@seekdb.example:2881/workspace_db"


def test_resolve_tapestore_url_prefers_bub_workspace_path(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text(
        "BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://workspace:secret@seekdb.example:2881/workspace_db\n",
        encoding="utf-8",
    )

    other_root = tmp_path / "other"
    nested = other_root / "nested"
    nested.mkdir(parents=True)
    (other_root / ".env").write_text(
        "BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://discovered:secret@seekdb.example:2881/discovered_db\n",
        encoding="utf-8",
    )

    with imported_bubseek_modules("bubseek.config") as [config_mod]:
        monkeypatch.setenv("BUB_WORKSPACE_PATH", str(workspace))
        url = config_mod.resolve_tapestore_url(discover_from=nested)

    assert url == "mysql+oceanbase://workspace:secret@seekdb.example:2881/workspace_db"


def test_resolve_tapestore_url_discovers_parent_env(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "project"
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    (root / ".env").write_text(
        "BUB_TAPESTORE_SQLALCHEMY_URL=mysql+oceanbase://discovered:secret@seekdb.example:2881/discovered_db\n",
        encoding="utf-8",
    )

    with imported_bubseek_modules("bubseek.config") as [config_mod]:
        monkeypatch.delenv("BUB_WORKSPACE_PATH", raising=False)
        url = config_mod.resolve_tapestore_url(discover_from=nested)

    assert url == "mysql+oceanbase://discovered:secret@seekdb.example:2881/discovered_db"


def test_ensure_database_skips_non_mysql_backends(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.database") as [database_mod]:
        monkeypatch.setattr(
            database_mod.BubSeekSettings,
            "from_workspace",
            lambda workspace=None: _settings_with_db_params(None),
        )
        create_called = False
        exists_called = False

        def _create_database(*args):
            nonlocal create_called
            create_called = True
            return True

        def _database_exists(*args):
            nonlocal exists_called
            exists_called = True
            return True

        monkeypatch.setattr(database_mod, "create_database", _create_database)
        monkeypatch.setattr(database_mod, "database_exists", _database_exists)

        database_mod.ensure_database()

    assert not exists_called
    assert not create_called


def test_ensure_database_returns_when_database_exists(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.database") as [database_mod]:
        monkeypatch.setattr(
            database_mod.BubSeekSettings,
            "from_workspace",
            lambda workspace=None: _settings_with_db_params(("seekdb.example", 2881, "seek", "secret", "analytics")),
        )
        create_called = False

        monkeypatch.setattr(database_mod, "database_exists", lambda *args: True)

        def _create_database(*args):
            nonlocal create_called
            create_called = True
            return True

        monkeypatch.setattr(database_mod, "create_database", _create_database)

        database_mod.ensure_database()

    assert not create_called


def test_ensure_database_creates_missing_database_without_prompt(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.database") as [database_mod]:
        monkeypatch.setattr(
            database_mod.BubSeekSettings,
            "from_workspace",
            lambda workspace=None: _settings_with_db_params(("seekdb.example", 2881, "seek", "secret", "analytics")),
        )
        monkeypatch.setattr(database_mod, "database_exists", lambda *args: False)
        monkeypatch.setattr(database_mod.sys.stdin, "isatty", lambda: False)

        created = False

        def _create_database(*args):
            nonlocal created
            created = True
            return True

        monkeypatch.setattr(database_mod, "create_database", _create_database)

        database_mod.ensure_database()

    assert created


def test_ensure_database_respects_tty_decline(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.database") as [database_mod]:
        monkeypatch.setattr(
            database_mod.BubSeekSettings,
            "from_workspace",
            lambda workspace=None: _settings_with_db_params(("seekdb.example", 2881, "seek", "secret", "analytics")),
        )
        monkeypatch.setattr(database_mod, "database_exists", lambda *args: False)
        monkeypatch.setattr(database_mod.sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(database_mod.typer, "confirm", lambda *args, **kwargs: False)

        with pytest.raises(database_mod.typer.Exit) as exc_info:
            database_mod.ensure_database()

    assert exc_info.value.exit_code == 1
