from __future__ import annotations

from pathlib import Path


def pdm_build_update_files(context, files: dict[str, Path]) -> None:
    if context.target != "wheel":
        return

    skills_root = context.root / "skills"
    if not skills_root.is_dir():
        return

    for path in sorted(skills_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(skills_root)
        files[(Path("bub_skills") / relative).as_posix()] = path
