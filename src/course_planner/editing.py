"""Manual edits to a plan.

Edits never refuse a move because it would break a rule: the student may want
to try it. Instead every edit is followed by ``planner.check_plan`` so the
problems are shown straight away. All functions return a new plan and leave the
input untouched.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from course_planner.models import Course
from course_planner.planner import Issue, PlanConstraints, course_credits

Semesters = list[list[str]]


def _copy(semesters: Sequence[Sequence[str]]) -> Semesters:
    return [list(sem) for sem in semesters]


def _trim(semesters: Semesters) -> Semesters:
    while semesters and not semesters[-1]:
        semesters.pop()
    return semesters


def find_course(semesters: Sequence[Sequence[str]], code: str) -> int | None:
    """Index of the semester holding ``code`` (the first one, if duplicated)."""
    for i, sem in enumerate(semesters):
        if code in sem:
            return i
    return None


def add_course(semesters: Sequence[Sequence[str]], code: str, target: int) -> Semesters:
    """Put ``code`` in semester ``target``; ``target == len(semesters)`` opens a new one."""
    plan = _copy(semesters)
    if not 0 <= target <= len(plan):
        raise ValueError(f"Semester {target + 1} does not exist.")
    if target == len(plan):
        plan.append([])
    plan[target].append(code)
    return plan


def remove_course(semesters: Sequence[Sequence[str]], code: str) -> Semesters:
    plan = _copy(semesters)
    source = find_course(plan, code)
    if source is None:
        raise ValueError(f"{code} is not in the plan.")
    plan[source].remove(code)
    return _trim(plan)


def move_course(semesters: Sequence[Sequence[str]], code: str, target: int) -> Semesters:
    """Move ``code`` to semester ``target`` (``len(semesters)`` opens a new semester)."""
    source = find_course(semesters, code)
    if source is None:
        raise ValueError(f"{code} is not in the plan.")
    if not 0 <= target <= len(semesters):
        raise ValueError(f"Semester {target + 1} does not exist.")
    if source == target:
        return _copy(semesters)
    plan = add_course(remove_course_keep_gaps(semesters, code), code, target)
    return _trim(plan)


def remove_course_keep_gaps(semesters: Sequence[Sequence[str]], code: str) -> Semesters:
    """Like ``remove_course`` but keeps empty semesters so indexes stay stable."""
    plan = _copy(semesters)
    source = find_course(plan, code)
    if source is None:
        raise ValueError(f"{code} is not in the plan.")
    plan[source].remove(code)
    return plan


@dataclass(frozen=True)
class SemesterSummary:
    index: int
    credits: int
    course_count: int
    difficulty: float
    problems: tuple[Issue, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def summarise(
    semesters: Sequence[Sequence[str]],
    catalog: Mapping[str, Course],
    difficulty: Mapping[str, float],
    constraints: PlanConstraints,
    issues: Sequence[Issue],
) -> list[SemesterSummary]:
    """Per-semester totals, with the problems ``check_plan`` attached to each semester."""
    summaries = []
    for i, sem in enumerate(semesters):
        known = [catalog[c] for c in sem if c in catalog]
        summaries.append(
            SemesterSummary(
                index=i,
                credits=sum(course_credits(c, constraints) for c in known),
                course_count=len(sem),
                difficulty=round(sum(difficulty.get(c, 0.0) for c in sem), 2),
                problems=tuple(issue for issue in issues if issue.semester == i),
            )
        )
    return summaries


def plan_wide_issues(issues: Sequence[Issue]) -> list[Issue]:
    """Problems that belong to no single semester (missing or duplicated courses)."""
    return [issue for issue in issues if issue.semester is None]
