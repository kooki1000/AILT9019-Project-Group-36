"""Parse free-text prerequisite expressions into AND-of-OR groups."""

from __future__ import annotations

import re

from course_planner.models import PrereqGroups

COURSE_CODE = r"[A-Z]{4}\d{4}[A-Z]?"
_CODE_RE = re.compile(COURSE_CODE)
_NONE_RE = re.compile(r"^\s*(none|nil|n/?a|-|—)?\s*$", re.IGNORECASE)
_AND_RE = re.compile(r"\s*(?:;|,|&|\band\b)\s*", re.IGNORECASE)
_OR_RE = re.compile(r"\s*(?:/|\bor\b)\s*", re.IGNORECASE)


def parse_prerequisites(text: str) -> PrereqGroups:
    """Turn ``"COMP1117 and (MATH1013 or MATH1853)"`` into AND-of-OR groups.

    The example gives ``(("COMP1117",), ("MATH1013", "MATH1853"))``.

    Commas, semicolons, ``&`` and ``and`` join groups; ``or`` and ``/`` join
    alternatives inside a group. Parentheses are ignored because the grammar is
    already flat (AND of ORs). Text without any course code (``None``, ``-``)
    yields no prerequisites. Duplicate groups and codes are removed while
    keeping the original order.
    """
    if _NONE_RE.match(text):
        return ()
    cleaned = text.replace("(", " ").replace(")", " ").upper()
    groups: list[tuple[str, ...]] = []
    for and_part in _AND_RE.split(cleaned):
        codes = [
            code
            for or_part in _OR_RE.split(and_part)
            for code in _CODE_RE.findall(or_part)
        ]
        group = tuple(dict.fromkeys(codes))
        if group and group not in groups:
            groups.append(group)
    return tuple(groups)
