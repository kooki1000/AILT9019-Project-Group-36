"""Command line for the document parser, used by the agent skill in ``skills/``.

    python -m course_planner.parse_cli requirements.pdf

Prints JSON with ``courses`` and ``warnings``. Exit code 0 on success, 1 when the
file could not be read or no courses were found, 2 for bad usage. Nothing is
stored and nothing leaves the machine.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from course_planner.parser import EmptyDocumentError, UnsupportedFileError, parse_document


def to_json(result) -> dict:
    return {
        "courses": [
            {
                "code": c.code,
                "title": c.title,
                "credits": c.credits,
                "assessments": c.assessments,
                "elective": c.elective,
                # AND of OR-groups: every inner list needs at least one course done.
                "prerequisites": [list(group) for group in c.prerequisites],
            }
            for c in result.courses
        ],
        "warnings": result.warnings,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m course_planner.parse_cli <PDF, .txt or .csv file>")
        return 2
    path = Path(args[0])
    try:
        result = parse_document(path)
    except (UnsupportedFileError, EmptyDocumentError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(to_json(result), indent=2, ensure_ascii=False))
    if not result.courses:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
