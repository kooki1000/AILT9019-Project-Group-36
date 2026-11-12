"""Entry point for the skill: ``python3 scripts/parse_requirements.py <file>``.

Uses the ``course_planner`` package bundled next to this script when the skill was
built with ``skills/build_skill.py``, otherwise the installed project package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from course_planner.parse_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
