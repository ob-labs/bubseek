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
    assert "bub-dingtalk" in optional["dingtalk"]
    assert "wechat" in optional
    assert "bub-wechat" in optional["wechat"]
    assert any("bub-tapestore-sqlalchemy" in d for d in deps)

    sources = data.get("tool", {}).get("uv", {}).get("sources", {})
    assert "bub" in sources
    assert sources["bub"].get("git") == "https://github.com/bubbuild/bub.git"
    assert "bub-dingtalk" in sources
    assert sources["bub-dingtalk"].get("git") == "https://github.com/bubbuild/bub-contrib.git"
    assert sources["bub-dingtalk"].get("subdirectory") == "packages/bub-dingtalk"
    assert "bub-feishu" in sources
    assert sources["bub-feishu"].get("git") == "https://github.com/bubbuild/bub-contrib.git"
    assert "bub-wechat" in sources
    assert sources["bub-wechat"].get("git") == "https://github.com/bubbuild/bub-contrib.git"
    assert sources["bub-wechat"].get("subdirectory") == "packages/bub-wechat"
    requires = data["build-system"]["requires"]
    assert "pdm-backend" in requires
    assert any("pdm-build-skills" in r for r in requires)


def test_pyproject_includes_builtin_skills_in_wheel() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["tool"]["pdm"]["build"]["includes"] == [
        "src/bubseek",
        "src/skills",
    ]
    skills = data["tool"]["pdm"]["build"]["skills"]
    assert skills == [
        {
            "git": "https://github.com/PsiACE/skills.git",
            "subpath": "skills",
            "include": ["friendly-python", "piglet"],
        },
        {
            "git": "https://github.com/bubbuild/bub-contrib.git",
            "subpath": ".agents/skills",
            "include": ["plugin-creator"],
        },
    ]


def test_bundled_skills_have_valid_frontmatter() -> None:
    skill_root = REPO_ROOT / "src" / "skills"
    skill_names = []

    for skill_dir in sorted(path for path in skill_root.iterdir() if path.is_dir()):
        metadata = _read_skill(skill_dir, source="builtin")
        assert metadata is not None
        skill_names.append(metadata.name)

    assert "github-repo-cards" in skill_names


def test_main_forwards_explicit_args(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.__main__", "bubseek.bootstrap") as [main_mod, bootstrap_mod]:
        observed_command: list[str] | None = None
        observed_env: dict[str, str] | None = None

        monkeypatch.setattr(bootstrap_mod.BubSeekBootstrap, "ensure_database", lambda self: None)
        monkeypatch.setattr(bootstrap_mod.shutil, "which", lambda _name: "/usr/bin/bub")

        def _capture_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
            nonlocal observed_command, observed_env
            observed_command = argv
            observed_env = env
            raise SystemExit(0)

        monkeypatch.setattr(bootstrap_mod.os, "execve", _capture_execve)
        with pytest.raises(SystemExit) as exc_info:
            main_mod.main(["chat", "--help"])
        assert exc_info.value.code == 0

    assert observed_command == ["/usr/bin/bub", "chat", "--help"]
    assert observed_env is not None


def test_main_defaults_to_help(monkeypatch) -> None:
    with imported_bubseek_modules("bubseek.__main__", "bubseek.bootstrap") as [main_mod, bootstrap_mod]:
        observed_command: list[str] | None = None

        monkeypatch.setattr(bootstrap_mod.BubSeekBootstrap, "ensure_database", lambda self: None)
        monkeypatch.setattr(bootstrap_mod.shutil, "which", lambda _name: "/usr/bin/bub")

        def _capture_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
            nonlocal observed_command
            observed_command = argv
            raise SystemExit(0)

        monkeypatch.setattr(bootstrap_mod.os, "execve", _capture_execve)
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

    with imported_bubseek_modules("bubseek.__main__", "bubseek.bootstrap") as [main_mod, bootstrap_mod]:
        observed_command: list[str] | None = None
        observed_env: dict[str, str] | None = None

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(bootstrap_mod.BubSeekBootstrap, "ensure_database", lambda self: None)
        monkeypatch.setattr(bootstrap_mod.shutil, "which", lambda _name: "/usr/bin/bub")

        def _capture_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
            nonlocal observed_command, observed_env
            observed_command = argv
            observed_env = env
            raise SystemExit(0)

        monkeypatch.setattr(bootstrap_mod.os, "execve", _capture_execve)
        with pytest.raises(SystemExit) as exc_info:
            main_mod.main(["chat"])
        assert exc_info.value.code == 0

    assert observed_command == ["/usr/bin/bub", "chat"]
    assert observed_env is not None
    assert observed_env["BUB_API_KEY"] == "demo-key"
    assert observed_env["BUB_API_BASE"] == "https://openrouter.ai/api/v1"
    assert observed_env["BUB_TAPESTORE_SQLALCHEMY_URL"].startswith("mysql+oceanbase://")


def test_wrapper_forwards_workspace_to_plugins(monkeypatch, tmp_path: Path) -> None:
    with imported_bubseek_modules("bubseek.__main__", "bubseek.bootstrap") as [main_mod, bootstrap_mod]:
        observed_env: dict[str, str] | None = None
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setattr(bootstrap_mod.BubSeekBootstrap, "ensure_database", lambda self: None)
        monkeypatch.setattr(bootstrap_mod.shutil, "which", lambda _name: "/usr/bin/bub")

        def _capture_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
            nonlocal observed_env
            observed_env = env
            raise SystemExit(0)

        monkeypatch.setattr(bootstrap_mod.os, "execve", _capture_execve)
        with pytest.raises(SystemExit):
            main_mod.main(["--workspace", str(workspace), "gateway", "--enable-channel", "marimo"])

    assert observed_env is not None
    assert observed_env["BUB_WORKSPACE_PATH"] == str(workspace.resolve())


def test_database_settings_default_to_oceanbase(monkeypatch, tmp_path: Path) -> None:
    with imported_bubseek_modules("bubseek.config") as [config_mod]:
        monkeypatch.setenv("BUB_HOME", str(tmp_path / "runtime-home"))
        monkeypatch.setenv("BUB_TAPESTORE_SQLALCHEMY_URL", "")  # override .env so default is used

        settings = config_mod.DatabaseSettings()

    assert settings.backend_name == "mysql"
    assert settings.mysql_connection_params() == (
        "127.0.0.1",
        2881,
        "root",
        "",
        "bub",
    )


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
