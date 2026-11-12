"""Parse free-text prerequisite expressions into AND-of-OR groups."""

from __future__ import annotations

import re

from course_planner.models import PrereqGroups

# ``XXXX1234`` is a placeholder for "some course", never a real code.
COURSE_CODE = r"(?!XXXX)[A-Z]{4}\d{4}[A-Z]?"
_CODE_RE = re.compile(COURSE_CODE)
_NONE_RE = re.compile(r"^\s*(none|nil|n/?a|-|—)?\s*$", re.IGNORECASE)
_AND_RE = re.compile(r"\s*(?:;|,|&|\band\b)\s*", re.IGNORECASE)
# Text after these phrases restricts the course but is not a prerequisite.
_CUT_RE = re.compile(
    r"\b(?:non-?permissible combinations?|mutually exclusive|co-?requisites?|not open to)\b.*$",
    re.IGNORECASE | re.DOTALL,
)
_OR_RE = re.compile(r"\s*(?:/|\bor\b)\s*", re.IGNORECASE)


def is_none_text(text: str) -> bool:
    """True for "None", "Nil", "-" and empty text: a stated absence of prerequisites."""
    return bool(_NONE_RE.match(text.strip().rstrip(".")))


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
    cleaned = _CUT_RE.sub("", text).replace("(", " ").replace(")", " ").upper()
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
