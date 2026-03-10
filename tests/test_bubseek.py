from __future__ import annotations

import importlib
import sys
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

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


def test_pyproject_pins_bub_and_bundled_plugins() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    deps = data["project"]["dependencies"]
    assert any("bub" in d for d in deps)
    assert any("bub-web-search" in d for d in deps)
    optional = data["project"].get("optional-dependencies", {})
    assert "feishu" in optional
    assert "bub-feishu" in optional["feishu"]
    assert "dingtalk" in optional
    assert "bubseek-dingtalk" in optional["dingtalk"]
    assert any("bub-tapestore-sqlalchemy" in d for d in deps)

    sources = data.get("tool", {}).get("uv", {}).get("sources", {})
    assert "bub-feishu" in sources
    assert sources["bub-feishu"].get("git") == "https://github.com/bubbuild/bub-contrib.git"
    assert "bubseek-dingtalk" in sources
    assert sources["bubseek-dingtalk"].get("workspace") is True
    requires = data["build-system"]["requires"]
    assert "pdm-backend" in requires
    assert any("pdm-build-bub" in r for r in requires)


def test_pyproject_includes_builtin_skills_in_wheel() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["tool"]["pdm"]["build"]["includes"] == [
        "src/bubseek",
        "src/bub_skills",
    ]


def test_bundled_skill_has_valid_frontmatter() -> None:
    skill_dir = REPO_ROOT / "src" / "bub_skills" / "bubseek-bootstrap"
    metadata = _read_skill(skill_dir, source="builtin")

    assert metadata is not None
    assert metadata.name == "bubseek-bootstrap"


def test_main_forwards_explicit_args(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.__main__", "bubseek.cli") as [main_mod, cli_mod]:
        observed_command: list[str] | None = None
        observed_env: dict[str, str] | None = None

        monkeypatch.setattr(cli_mod.shutil, "which", lambda _name: "/usr/bin/bub")

        def _capture_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
            nonlocal observed_command, observed_env
            observed_command = argv
            observed_env = env
            raise SystemExit(0)

        monkeypatch.setattr(cli_mod.os, "execve", _capture_execve)
        with pytest.raises(SystemExit) as exc_info:
            main_mod.main(["chat", "--help"])
        assert exc_info.value.code == 0

    assert observed_command == ["/usr/bin/bub", "chat", "--help"]
    assert observed_env is not None


def test_main_defaults_to_help(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.__main__", "bubseek.cli") as [main_mod, cli_mod]:
        observed_command: list[str] | None = None

        monkeypatch.setattr(cli_mod.shutil, "which", lambda _name: "/usr/bin/bub")

        def _capture_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
            nonlocal observed_command
            observed_command = argv
            raise SystemExit(0)

        monkeypatch.setattr(cli_mod.os, "execve", _capture_execve)
        with pytest.raises(SystemExit) as exc_info:
            main_mod.main([])
        assert exc_info.value.code == 0

    assert observed_command == ["/usr/bin/bub", "--help"]


def test_wrapper_forwards_dotenv_values(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join([
            "BUB_API_KEY=demo-key",
            "BUB_API_BASE=https://openrouter.ai/api/v1",
        ]),
        encoding="utf-8",
    )

    with imported_bubseek_modules("bubseek.__main__", "bubseek.cli") as [main_mod, cli_mod]:
        observed_command: list[str] | None = None
        observed_env: dict[str, str] | None = None

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli_mod.shutil, "which", lambda _name: "/usr/bin/bub")

        def _capture_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
            nonlocal observed_command, observed_env
            observed_command = argv
            observed_env = env
            raise SystemExit(0)

        monkeypatch.setattr(cli_mod.os, "execve", _capture_execve)
        with pytest.raises(SystemExit) as exc_info:
            main_mod.main(["chat"])
        assert exc_info.value.code == 0

    assert observed_command == ["/usr/bin/bub", "chat"]
    assert observed_env is not None
    assert observed_env["BUB_API_KEY"] == "demo-key"
    assert observed_env["BUB_API_BASE"] == "https://openrouter.ai/api/v1"
