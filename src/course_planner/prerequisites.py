"""Parse free-text prerequisite expressions into AND-of-OR groups.

``"COMP1117 and (MATH1013 or MATH1853)"`` becomes ``(("COMP1117",), ("MATH1013", "MATH1853"))``:
the course is unlocked when every group has at least one course completed. Real syllabuses
also write ``"A or (B and C)"``; that is converted by distribution into
``((A, B), (A, C))``, which says the same thing in the same form.
"""

from __future__ import annotations

import re

from course_planner.models import PrereqGroups

# ``XXXX1234`` is a placeholder for "some course", never a real code.
COURSE_CODE = r"(?!XXXX)[A-Z]{4}\d{4}[A-Z]?"
_CODE_RE = re.compile(COURSE_CODE)
_NONE_RE = re.compile(r"^\s*(none|nil|n/?a|-|—)?\s*$", re.IGNORECASE)
# Text after these phrases restricts the course but is not a prerequisite.
_CUT_RE = re.compile(
    r"\b(?:non-?permissible combinations?|mutually exclusive|co-?requisites?|not open to)\b.*$",
    re.IGNORECASE | re.DOTALL,
)
# "... or take MATH1011 and MATH1853 concurrently": taking courses together is not a prerequisite.
_CONCURRENT_RE = re.compile(
    r"(?:,\s*)?(?:or\s+)?take\b[^.;]*?\bconcurrently\b[^.;]*", re.IGNORECASE
)
# ", or ..." continues the same list of alternatives, it does not start a new requirement.
_COMMA_OR_RE = re.compile(r",\s*or\b", re.IGNORECASE)
# Words of an alternative that is an exam result or level, not a course: the requirement can
# be met without any course in the group.
_QUALIFICATION_RE = re.compile(
    r"^(?:LEVEL|GRADE|PASS|HKDSE|MODULE|SCORE|IELTS|TOEFL|A-?LEVEL|GCE)$"
)
# "(Grade B or above)" right after a course says how well to pass it; it is not another route.
_REMARK_RE = re.compile(r"\(\s*(?:minimum\s+)?(?:grade|level|score|pass)\b[^()]*\)", re.IGNORECASE)
# "and either A or B", "and one of ...": an "and" that really joins two requirements.
_REQUIREMENT_WORDS = {"EITHER", "BOTH", "ANY", "ONE", "ALL", "AT"}
_PUNCTUATION_RE = re.compile(r"[^\w()/;,&\-]")  # quotes, full stops, brackets of other kinds
_TOKEN_RE = re.compile(rf"\(|\)|;|,|&|/|{COURSE_CODE}|[^\s()/;,&]+")

_QUAL = "?"  # stands for "an exam level or grade" inside a clause
_MAX_CLAUSES = 24

Clause = tuple[str, ...]
Cnf = list[Clause]


def is_none_text(text: str) -> bool:
    """True for "None", "Nil", "-" and empty text: a stated absence of prerequisites."""
    return bool(_NONE_RE.match(text.strip().rstrip(".")))


def parse_prerequisites(text: str) -> PrereqGroups:
    """Turn ``"COMP1117 and (MATH1013 or MATH1853)"`` into AND-of-OR groups.

    The example gives ``(("COMP1117",), ("MATH1013", "MATH1853"))``.

    ``and``, semicolons, ``&`` and commas join requirements; ``or`` and ``/`` join
    alternatives (so does ``", or"``); parentheses group. An ``and`` only joins requirements
    when a course code follows it, so the "and" in ``"ENGG1111 Programming and applications"``
    is part of a title. A requirement with an alternative that is an exam level or grade
    ("Level 2 in HKDSE Mathematics, or MATH1011") is dropped, because it can be met without
    any course; the caller reports the text as not fully checked. Duplicate groups and groups
    implied by a smaller one are removed. Text without any course code (``None``, ``-``)
    yields no prerequisites.
    """
    return parse_prerequisites_detailed(text)[0]


def parse_prerequisites_detailed(text: str) -> tuple[PrereqGroups, PrereqGroups]:
    """Like ``parse_prerequisites``, plus the "soft" groups that were dropped.

    A soft group has an alternative that needs no course ("GRMN1001 or comparable level
    acquired elsewhere"). It is not a hard requirement, but when one of its courses is part
    of the programme the planner can still use it to order courses; the caller decides.
    """
    if _NONE_RE.match(text):
        return (), ()
    cleaned = _CONCURRENT_RE.sub("", _CUT_RE.sub("", text))
    cleaned = _COMMA_OR_RE.sub(" or", cleaned)
    cleaned = _REMARK_RE.sub(_drop_remark, cleaned).upper()
    try:
        cnf = _Parser(_tokens(cleaned)).parse()
    except _Unbalanced:
        cnf = _flat(cleaned)
    return _finish(cnf)


def _joins_requirements(raw: list[str], index: int) -> bool:
    following = next((t for t in raw[index + 1 :] if t != "("), "")
    return _CODE_RE.fullmatch(following) is not None or following in _REQUIREMENT_WORDS


def _drop_remark(match: re.Match[str]) -> str:
    """Remove a "(Grade B or above)" remark, unless it names a course (then it is a real option)."""
    return match.group(0) if _CODE_RE.search(match.group(0).upper()) else " "


def _tokens(text: str) -> list[str]:
    """Codes, brackets, connectors (``AND`` / ``OR``) and a marker for exam levels.

    Other words belong to course titles or to conditions that cannot be checked ("OR
    EQUIVALENT") and are dropped. An ``AND`` is kept only when a code comes next.
    """
    raw = _TOKEN_RE.findall(_PUNCTUATION_RE.sub(" ", text))
    out: list[str] = []
    for index, token in enumerate(raw):
        if _CODE_RE.fullmatch(token) or token in ("(", ")"):
            out.append(token)
        elif token in (";", "&", ",") or (token == "AND" and _joins_requirements(raw, index)):
            out.append("AND")
        elif token in ("/", "OR"):
            out.append("OR")
        elif _QUALIFICATION_RE.match(token) and (not out or out[-1] != _QUAL):
            out.append(_QUAL)
    # "Pass in MATH1011" (level before a code) and "MATH1011 with grade B" (level after one)
    # only describe the course; they are not a way around it.
    def modifier(position: int) -> bool:
        before = out[position - 1] if position else ""
        after = out[position + 1] if position + 1 < len(out) else ""
        return _CODE_RE.fullmatch(after) is not None or _CODE_RE.fullmatch(before) is not None

    return [
        token for position, token in enumerate(out) if not (token == _QUAL and modifier(position))
    ]


class _Unbalanced(Exception):
    pass


class _Parser:
    """Recursive descent over ``and`` / ``or`` / brackets, producing a CNF clause list."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.at = 0

    def parse(self) -> Cnf:
        cnf = self._and()
        if self.at != len(self.tokens):
            raise _Unbalanced
        return cnf

    def _peek(self) -> str | None:
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def _and(self) -> Cnf:
        parts = [self._or()]
        while self._peek() == "AND":
            while self._peek() == "AND":  # "; and" is a single connector
                self.at += 1
            if self._peek() in (None, ")"):
                break
            parts.append(self._or())
        return [clause for part in parts for clause in part]

    def _or(self) -> Cnf:
        result = self._atom()
        # Alternatives are joined by "or", or simply written one after another.
        while self._peek() not in (None, ")", "AND"):
            while self._peek() == "OR":
                self.at += 1
            if self._peek() in (None, ")", "AND"):
                break
            result = _distribute(result, self._atom())
        return result

    def _atom(self) -> Cnf:
        token = self._peek()
        if token is None or token in (")", "AND", "OR"):
            return []
        self.at += 1
        if token == "(":
            inner = self._and()
            if self._peek() != ")":
                raise _Unbalanced
            self.at += 1
            return inner
        return [(token,)]


def _distribute(left: Cnf, right: Cnf) -> Cnf:
    """``(a and b) or (c and d)`` in CNF: each clause of one joined to each clause of the other."""
    if not left:
        return right
    if not right:
        return left
    if len(left) * len(right) > _MAX_CLAUSES:
        return left + right  # too tangled to expand; keep both sides as separate requirements
    return [tuple(dict.fromkeys(a + b)) for a in left for b in right]


def _flat(text: str) -> Cnf:
    """Fallback for unbalanced brackets: split on and/commas, brackets ignored."""
    cnf: Cnf = []
    flat = text.replace("(", " ").replace(")", " ")
    for part in re.split(r"\s*(?:;|,|&|\band\b)\s*", flat, flags=re.IGNORECASE):
        clause = tuple(dict.fromkeys(_CODE_RE.findall(part)))
        if clause:
            cnf.append(clause)
    return cnf


def _finish(cnf: Cnf) -> tuple[PrereqGroups, PrereqGroups]:
    """Split off clauses met without a course, then drop duplicates and implied clauses."""
    hard: list[Clause] = []
    soft: list[Clause] = []
    for clause in cnf:
        if _QUAL in clause:
            codes = tuple(c for c in clause if c != _QUAL)
            if codes and codes not in soft:
                soft.append(codes)
        elif clause and clause not in hard:
            hard.append(clause)
    kept = tuple(
        clause
        for clause in hard
        if not any(set(other) < set(clause) for other in hard)  # (A) makes (A or B) redundant
    )
    return kept, tuple(soft)
