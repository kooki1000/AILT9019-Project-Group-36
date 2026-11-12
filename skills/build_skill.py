"""Build ``dist/parse-requirements.zip``, a self-contained upload for Claude and ChatGPT.

    python skills/build_skill.py

The zip holds the skill folder as its top level (as Claude requires) and bundles the
few parser modules under ``scripts/course_planner/`` so the skill runs without
installing this project. The modules are copied from ``src/``, never edited by hand.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = "parse-requirements"
SKILL_DIR = ROOT / "skills" / SKILL
PACKAGE = ROOT / "src" / "course_planner"
BUNDLED_MODULES = ["__init__.py", "models.py", "prerequisites.py", "parser.py", "parse_cli.py"]


def skill_files() -> dict[str, Path]:
    """Map each path inside the zip (below the skill folder) to its source file."""
    files = {
        str(path.relative_to(SKILL_DIR)): path
        for path in sorted(SKILL_DIR.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    for module in BUNDLED_MODULES:
        files[f"scripts/course_planner/{module}"] = PACKAGE / module
    return files


def build(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, source in skill_files().items():
            archive.write(source, f"{SKILL}/{name}")
    return destination


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else ROOT / "dist" / f"{SKILL}.zip"
    print(f"Wrote {build(target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
