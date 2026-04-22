from __future__ import annotations

import importlib
import sys
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from bub.skills import _read_skill
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def imported_bubseek_modules(*module_names: str) -> Iterator[list[ModuleType]]:
    try:
        yield [importlib.import_module(name) for name in module_names]
    finally:
        for module_name in list(sys.modules):
            if module_name == "bubseek" or module_name.startswith("bubseek."):
                sys.modules.pop(module_name, None)
            if module_name == "bub_schedule_sqlalchemy" or module_name.startswith("bub_schedule_sqlalchemy."):
                sys.modules.pop(module_name, None)


def _load_pyproject() -> dict[str, object]:
    return _as_dict(tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")))


def _as_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_distribution_metadata_exposes_sqlalchemy_dialect_without_console_script() -> None:
    data = _load_pyproject()

    project = _as_dict(data["project"])
    assert "scripts" not in project
    assert project["entry-points"] == {
        "sqlalchemy.dialects": {
            "mysql.oceanbase": "bubseek.oceanbase:OceanBaseDialect",
        },
    }


def test_pyproject_includes_package_and_builtin_skills_in_wheel() -> None:
    data = _load_pyproject()

    tool = _as_dict(data["tool"])
    pdm = _as_dict(tool["pdm"])
    build = _as_dict(pdm["build"])
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


def test_mysql_connection_params_extract_mysql_values(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.oceanbase") as [oceanbase_mod]:
        monkeypatch.setenv(
            "BUB_TAPESTORE_SQLALCHEMY_URL",
            "mysql+pymysql://seek:secret@seekdb.example:2881/analytics",
        )

        assert oceanbase_mod.resolve_tapestore_url() == "mysql+oceanbase://seek:secret@seekdb.example:2881/analytics"
        assert oceanbase_mod.mysql_connection_params() == (
            "seekdb.example",
            2881,
            "seek",
            "secret",
            "analytics",
        )


def test_oceanbase_registers_mysql_pymysql_alias() -> None:
    with imported_bubseek_modules("bubseek.oceanbase") as [oceanbase_mod]:
        from sqlalchemy.dialects import registry

        dialect_cls = registry.load("mysql.oceanbase")

    assert dialect_cls is oceanbase_mod.OceanBaseDialect


def test_bubseek_settings_require_tapestore_url(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.settings") as [settings_mod]:
        monkeypatch.delenv("BUB_TAPESTORE_SQLALCHEMY_URL", raising=False)

        with pytest.raises(ValidationError):
            settings_mod.BubseekSettings(_env_file=None)


def test_bubseek_settings_normalize_tapestore_url(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.settings") as [settings_mod]:
        monkeypatch.setenv(
            "BUB_TAPESTORE_SQLALCHEMY_URL",
            "mysql+pymysql://seek:secret@seekdb.example:2881/analytics",
        )

        settings = settings_mod.load_bubseek_settings()

    assert settings.tapestore_url == "mysql+oceanbase://seek:secret@seekdb.example:2881/analytics"


def test_ensure_database_skips_non_mysql_backends(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.oceanbase") as [oceanbase_mod]:
        monkeypatch.setattr(oceanbase_mod, "mysql_connection_params", lambda *_: None)
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

        monkeypatch.setattr(oceanbase_mod, "create_database", _create_database)
        monkeypatch.setattr(oceanbase_mod, "database_exists", _database_exists)

        oceanbase_mod.ensure_database()

    assert not exists_called
    assert not create_called


def test_ensure_database_returns_when_database_exists(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.oceanbase") as [oceanbase_mod]:
        monkeypatch.setattr(
            oceanbase_mod,
            "mysql_connection_params",
            lambda *_: ("seekdb.example", 2881, "seek", "secret", "analytics"),
        )
        create_called = False

        monkeypatch.setattr(oceanbase_mod, "database_exists", lambda *args: True)

        def _create_database(*args):
            nonlocal create_called
            create_called = True
            return True

        monkeypatch.setattr(oceanbase_mod, "create_database", _create_database)

        oceanbase_mod.ensure_database()

    assert not create_called


def test_ensure_database_creates_missing_database_without_prompt(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.oceanbase") as [oceanbase_mod]:
        monkeypatch.setattr(
            oceanbase_mod,
            "mysql_connection_params",
            lambda *_: ("seekdb.example", 2881, "seek", "secret", "analytics"),
        )
        monkeypatch.setattr(oceanbase_mod, "database_exists", lambda *args: False)
        monkeypatch.setattr(oceanbase_mod.sys.stdin, "isatty", lambda: False)

        created = False

        def _create_database(*args):
            nonlocal created
            created = True
            return True

        monkeypatch.setattr(oceanbase_mod, "create_database", _create_database)

        oceanbase_mod.ensure_database()

    assert created


def test_ensure_database_respects_tty_decline(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.oceanbase") as [oceanbase_mod]:
        monkeypatch.setattr(
            oceanbase_mod,
            "mysql_connection_params",
            lambda *_: ("seekdb.example", 2881, "seek", "secret", "analytics"),
        )
        monkeypatch.setattr(oceanbase_mod, "database_exists", lambda *args: False)
        monkeypatch.setattr(oceanbase_mod.sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(oceanbase_mod.typer, "confirm", lambda *args, **kwargs: False)

        with pytest.raises(oceanbase_mod.typer.Exit) as exc_info:
            oceanbase_mod.ensure_database()

    assert exc_info.value.exit_code == 1
