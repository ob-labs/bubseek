"""Canonical marimo notebook templates for Bubseek insights."""

from __future__ import annotations

from pathlib import Path

NOTEBOOK_NAMES = frozenset({"dashboard.py", "index.py"})

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
SEED_NOTEBOOK_FILES = ("dashboard.py", "index.py", "example_visualization.py")


def get_seed_notebook_content(name: str) -> str:
    """Return the full content of a seed notebook template by file name."""
    path = _TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8")


def ensure_seed_notebooks(insights_dir: Path) -> list[Path]:
    """Write the canonical dashboard and starter notebooks into the insights directory."""
    insights_dir.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []
    for name in SEED_NOTEBOOK_FILES:
        path = insights_dir / name
        path.write_text(get_seed_notebook_content(name), encoding="utf-8")
        created_paths.append(path)
    return created_paths
