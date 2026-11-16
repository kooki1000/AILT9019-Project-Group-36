"""Build and check multi-semester plans.

Planning works in three stages:

1. **Screen** the remaining courses. Courses that can never be scheduled
   (circular prerequisites, a prerequisite that is missing from the document,
   a course bigger than the credit limit, ...) are reported as ``Issue`` objects
   and listed in ``PlanResult.unscheduled``. They are never dropped silently
   and never forced into the plan.
2. **Order** the schedulable courses by prerequisites (a course is only placed
   after one course from every prerequisite group), then **balance** difficulty
   greedily across the fewest semesters that work, and polish with a small
   local search that moves/swaps courses while the plan stays valid.
3. **Check**: ``check_plan`` validates any plan, including one the student has
   edited by hand, against the same rules.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from course_planner.metrics import DEFAULT_DIFFICULTY, load_variance
from course_planner.models import Course


class IssueKind(str, Enum):
    # Course cannot be scheduled at all.
    CYCLE = "circular_prerequisite"
    MISSING_PREREQUISITE = "missing_prerequisite"
    BLOCKED = "blocked_by_unschedulable_course"
    TOO_LARGE = "exceeds_credit_limit"
    NO_ROOM = "does_not_fit_in_remaining_semesters"
    # Problems in a concrete plan (see ``check_plan``).
    DUPLICATE = "scheduled_more_than_once"
    MISSING_COURSE = "required_course_missing"
    UNKNOWN_COURSE = "unknown_course"
    PREREQ_ORDER = "prerequisite_not_completed_first"
    CREDIT_LIMIT = "semester_over_credit_limit"
    COURSE_LIMIT = "semester_over_course_limit"


@dataclass(frozen=True)
class Issue:
    """A problem the student must be told about, in plain words."""

    kind: IssueKind
    courses: tuple[str, ...]
    message: str
    # 0-based semester index for plan-level problems, else ``None``.
    semester: int | None = None


@dataclass(frozen=True)
class PlanConstraints:
    max_credits: int = 24  # per semester
    max_courses: int = 5  # per semester
    max_semesters: int = 8
    # Credits assumed for a course whose document does not state them.
    default_credits: int = 6

    def __post_init__(self) -> None:
        for name in ("max_credits", "max_courses", "max_semesters", "default_credits"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")


@dataclass
class PlanResult:
    semesters: list[list[str]] = field(default_factory=list)
    unscheduled: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    # Courses in document order, as one would plan without balancing.
    baseline: list[list[str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every required course is scheduled and nothing is flagged."""
        return not self.issues and not self.unscheduled


def course_credits(course: Course, constraints: PlanConstraints) -> int:
    return course.credits if course.credits is not None else constraints.default_credits


def generate_plan(
    courses: Sequence[Course],
    completed: Collection[str] = (),
    difficulty: Mapping[str, float] | None = None,
    constraints: PlanConstraints = PlanConstraints(),  # noqa: B008 - frozen, safe to share
    pinned: Mapping[str, int] | None = None,
    windows: Mapping[str, tuple[int, int]] | None = None,
) -> PlanResult:
    """Plan the courses the student still needs.

    ``courses`` is the parsed requirement document in document order;
    ``completed`` are course codes already finished; ``difficulty`` maps course
    code to a 1-10 score (missing entries use a mid-range value). ``pinned``
    fixes a course in a semester (code to a 0-based semester index), for a course
    that is only offered in a given semester or runs across two; the planner
    arranges everything else around it. ``windows`` limits a course to a range of
    semesters (code to first and last 0-based index, both included), for a course
    that belongs to one year of study.
    """
    done = set(completed)
    difficulty = difficulty or {}
    required: list[Course] = []
    seen: set[str] = set()
    for course in courses:
        if course.code not in done and course.code not in seen:
            seen.add(course.code)
            required.append(course)

    schedulable, levels, issues = _screen(required, done, constraints)
    result = PlanResult(issues=issues)
    codes = {c.code for c in schedulable}
    pins = {code: i for code, i in (pinned or {}).items() if code in codes}
    for code, index in pins.items():
        if not 0 <= index < constraints.max_semesters:
            raise ValueError(f"{code} is pinned to semester {index + 1}, which is not in the plan")
    wins = {code: w for code, w in (windows or {}).items() if code in codes}
    for code, (first, last) in wins.items():
        if not 0 <= first <= last < constraints.max_semesters:
            raise ValueError(f"{code} has a semester range outside the plan")
    baseline, _ = baseline_plan(
        schedulable,
        done,
        constraints,
        max_semesters=len(schedulable) + len(pins) + 1,
        pinned=pins,
        windows=wins,
    )
    result.baseline = baseline

    if schedulable:
        by_code = {c.code: c for c in schedulable}
        semesters = _best_balanced(
            schedulable, levels, done, difficulty, constraints, baseline, pins, wins
        )
        if semesters is None or check_plan(semesters, by_code, done, constraints):
            # No balanced plan in the allowed range (or, defensively, an invalid
            # one). The baseline is valid by construction, so use it, cut off at
            # the semester limit.
            semesters = [list(s) for s in baseline[: constraints.max_semesters]]
        elif len(baseline) == len(semesters) and (
            load_variance(baseline, difficulty) < load_variance(semesters, difficulty)
        ):
            # The balancing is a heuristic. When document order happens to be more even over
            # the same number of semesters, use it, so "balanced" is never worse than the
            # baseline it is compared with.
            semesters = [list(s) for s in baseline]
        placed = {code for sem in semesters for code in sem}
        leftover = [c.code for c in schedulable if c.code not in placed]
        if leftover:
            result.issues.append(
                Issue(
                    IssueKind.NO_ROOM,
                    tuple(leftover),
                    f"{_join(leftover)} cannot fit in {constraints.max_semesters} semesters "
                    "within the prerequisite order and the per-semester load limit.",
                )
            )
        order = {c.code: i for i, c in enumerate(schedulable)}
        result.semesters = [sorted(sem, key=order.__getitem__) for sem in semesters]

    placed = {code for sem in result.semesters for code in sem}
    result.unscheduled = [c.code for c in required if c.code not in placed]
    return result


def baseline_plan(
    courses: Sequence[Course],
    completed: Collection[str],
    constraints: PlanConstraints,
    max_semesters: int | None = None,
    pinned: Mapping[str, int] | None = None,
    windows: Mapping[str, tuple[int, int]] | None = None,
) -> tuple[list[list[str]], list[str]]:
    """Fill each semester with courses in document order, respecting prerequisites and limits.

    Pinned courses go in their semester first. Returns ``(semesters, leftover_codes)``. This is
    the reference the balanced plan is compared against.
    """
    limit = constraints.max_semesters if max_semesters is None else max_semesters
    done = set(completed)
    pins = dict(pinned or {})
    by_code = {c.code: c for c in courses}
    pinned_at: dict[int, list[Course]] = {}
    for code, index in pins.items():
        if code in by_code:
            pinned_at.setdefault(index, []).append(by_code[code])
    wins = dict(windows or {})
    remaining = [c for c in courses if c.code not in pins]
    starts = (wins[c.code][0] for c in remaining if c.code in wins)
    last_pin = max(max(pinned_at, default=-1), max(starts, default=-1))
    semesters: list[list[str]] = []
    while (remaining or len(semesters) <= last_pin) and len(semesters) < limit:
        index = len(semesters)
        sem: list[Course] = list(pinned_at.get(index, []))
        credits = sum(course_credits(c, constraints) for c in sem)
        # A course whose semester range ends now goes first; one whose range has not started waits.
        due_first = sorted(remaining, key=lambda c: wins.get(c.code, (0, -1))[1] != index)
        for course in due_first:
            first = wins.get(course.code, (0, index))[0]
            cr = course_credits(course, constraints)
            if (
                first <= index
                and _satisfied(course, done)
                and credits + cr <= constraints.max_credits
                and len(sem) < constraints.max_courses
            ):
                sem.append(course)
                credits += cr
        if not sem and index > last_pin:
            break
        placed = {c.code for c in sem}
        semesters.append([c.code for c in sem])
        done |= placed
        remaining = [c for c in remaining if c.code not in placed]
    return semesters, [c.code for c in remaining]


def check_plan(
    semesters: Sequence[Sequence[str]],
    catalog: Mapping[str, Course],
    completed: Collection[str] = (),
    constraints: PlanConstraints = PlanConstraints(),  # noqa: B008
    required: Iterable[str] | None = None,
) -> list[Issue]:
    """Validate a plan (generated or hand-edited); an empty list means it is valid.

    Checks that every course in ``required`` appears exactly once, that no course
    comes before its prerequisites, and that no semester exceeds the credit or
    course-count limit. Courses outside ``catalog`` are reported, not ignored.
    """
    issues: list[Issue] = []
    positions: dict[str, list[int]] = {}
    for i, sem in enumerate(semesters):
        for code in sem:
            positions.setdefault(code, []).append(i)

    for code, where in positions.items():
        if len(where) > 1:
            issues.append(
                Issue(
                    IssueKind.DUPLICATE,
                    (code,),
                    f"{code} is scheduled {len(where)} times "
                    f"(semesters {', '.join(str(i + 1) for i in where)}).",
                )
            )
        if code not in catalog:
            issues.append(
                Issue(IssueKind.UNKNOWN_COURSE, (code,), f"{code} is not a known course.", where[0])
            )
    for code in required or ():
        if code not in positions:
            issues.append(
                Issue(
                    IssueKind.MISSING_COURSE, (code,), f"{code} is required but is not in the plan."
                )
            )

    done = set(completed)
    for i, sem in enumerate(semesters):
        known = [catalog[code] for code in sem if code in catalog]
        credits = sum(course_credits(c, constraints) for c in known)
        if credits > constraints.max_credits:
            issues.append(
                Issue(
                    IssueKind.CREDIT_LIMIT,
                    tuple(sem),
                    f"Semester {i + 1} has {credits} credits; "
                    f"the limit is {constraints.max_credits}.",
                    i,
                )
            )
        if len(sem) > constraints.max_courses:
            issues.append(
                Issue(
                    IssueKind.COURSE_LIMIT,
                    tuple(sem),
                    f"Semester {i + 1} has {len(sem)} courses; "
                    f"the limit is {constraints.max_courses}.",
                    i,
                )
            )
        for course in known:
            for group in course.prerequisites:
                if not any(member in done for member in group):
                    issues.append(
                        Issue(
                            IssueKind.PREREQ_ORDER,
                            (course.code, *group),
                            f"{course.code} (semester {i + 1}) needs {_either(group)} "
                            "completed in an earlier semester.",
                            i,
                        )
                    )
        done.update(sem)
    return issues


# --------------------------------------------------------------------------- screening


def _satisfied(course: Course, done: Collection[str]) -> bool:
    return all(any(member in done for member in group) for group in course.prerequisites)


def _join(codes: Iterable[str]) -> str:
    return ", ".join(codes)


def _either(group: Sequence[str]) -> str:
    return group[0] if len(group) == 1 else f"one of {_join(group)}"


def _screen(
    required: Sequence[Course], completed: set[str], constraints: PlanConstraints
) -> tuple[list[Course], dict[str, int], list[Issue]]:
    """Split ``required`` into schedulable courses (with their depth) and issues."""
    issues: list[Issue] = []

    candidates: list[Course] = []
    for course in required:
        credits = course_credits(course, constraints)
        if credits > constraints.max_credits:
            issues.append(
                Issue(
                    IssueKind.TOO_LARGE,
                    (course.code,),
                    f"{course.code} is {credits} credits, more than the "
                    f"{constraints.max_credits}-credit semester limit.",
                )
            )
        else:
            candidates.append(course)

    # Repeatedly schedule everything whose prerequisites are met, ignoring the
    # load limit. Whatever never becomes ready can never be scheduled.
    level: dict[str, int] = {}
    reached = set(completed)
    pending = list(candidates)
    depth = 0
    while True:
        ready = [c for c in pending if _satisfied(c, reached)]
        if not ready:
            break
        for course in ready:
            level[course.code] = depth
        reached.update(c.code for c in ready)
        pending = [c for c in pending if c.code not in level]
        depth += 1

    issues.extend(_explain_blocked(pending, required, completed, reached))
    schedulable = [c for c in candidates if c.code in level]
    return schedulable, level, issues


def _explain_blocked(
    blocked: Sequence[Course], required: Sequence[Course], completed: set[str], reached: set[str]
) -> list[Issue]:
    blocked_codes = {c.code for c in blocked}
    known = {c.code for c in required} | completed
    unmet = {
        c.code: [g for g in c.prerequisites if not any(m in reached for m in g)] for c in blocked
    }
    edges = {
        code: sorted({m for g in groups for m in g if m in blocked_codes})
        for code, groups in unmet.items()
    }

    issues: list[Issue] = []
    in_cycle: set[str] = set()
    for members in _cycles(edges):
        in_cycle.update(members)
        issues.append(
            Issue(
                IssueKind.CYCLE,
                tuple(members),
                f"Circular prerequisite: {_join(members)} each depend on one another, "
                "so none of them can be scheduled.",
            )
        )

    for course in blocked:
        missing = [g for g in unmet[course.code] if not any(m in known for m in g)]
        for group in missing:
            issues.append(
                Issue(
                    IssueKind.MISSING_PREREQUISITE,
                    (course.code,),
                    f"{course.code} needs {_either(group)}, which is not in the requirement "
                    "document or your completed courses.",
                )
            )
        if not missing and course.code not in in_cycle:
            waiting = sorted({m for g in unmet[course.code] for m in g if m in known})
            issues.append(
                Issue(
                    IssueKind.BLOCKED,
                    (course.code,),
                    f"{course.code} cannot be scheduled because it depends on "
                    f"{_join(waiting)}, which cannot be scheduled.",
                )
            )
    return issues


def _cycles(edges: Mapping[str, Sequence[str]]) -> list[list[str]]:
    """Strongly connected components that contain a cycle (Tarjan), sorted for stable output."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []

    def visit(node: str) -> None:
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        for nxt in edges.get(node, ()):
            if nxt not in index:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1 or node in edges.get(node, ()):
                found.append(sorted(component))

    for node in edges:
        if node not in index:
            visit(node)
    return sorted(found)


# --------------------------------------------------------------------------- balancing


def _heights(schedulable: Sequence[Course], level: Mapping[str, int]) -> dict[str, int]:
    """Length of the longest chain of courses that must follow each course."""
    dependents: dict[str, list[str]] = {c.code: [] for c in schedulable}
    for course in schedulable:
        for prereq in course.prerequisite_codes:
            if prereq in level and level[prereq] < level[course.code]:
                dependents[prereq].append(course.code)
    height: dict[str, int] = {}
    for course in sorted(schedulable, key=lambda c: -level[c.code]):
        height[course.code] = max((1 + height[d] for d in dependents[course.code]), default=0)
    return height


def _best_balanced(
    schedulable: Sequence[Course],
    level: Mapping[str, int],
    completed: set[str],
    difficulty: Mapping[str, float],
    constraints: PlanConstraints,
    baseline: Sequence[Sequence[str]],
    pinned: Mapping[str, int],
    windows: Mapping[str, tuple[int, int]],
) -> list[list[str]] | None:
    """Balanced plan over the fewest semesters that work, or ``None``."""
    total_credits = sum(course_credits(c, constraints) for c in schedulable)
    lower_bound = max(
        max(level.values()) + 1,
        math.ceil(total_credits / constraints.max_credits),
        math.ceil(len(schedulable) / constraints.max_courses),
        max(pinned.values(), default=-1) + 1,
    )
    height = _heights(schedulable, level)
    for n in range(lower_bound, min(len(baseline), constraints.max_semesters) + 1):
        # The balanced build can run out of semesters when long prerequisite chains are left
        # until late, so if it fails try again starting the longest chains first.
        for critical_first in (False, True):
            built = _build_balanced(
                schedulable, height, completed, difficulty, constraints, n, pinned,
                windows, critical_first,
            )
            if built is not None and _in_windows(built, windows):
                return _improve(
                    built, schedulable, completed, difficulty, constraints, pinned, baseline,
                    windows,
                )
    return None


def _build_balanced(
    schedulable: Sequence[Course],
    height: Mapping[str, int],
    completed: set[str],
    difficulty: Mapping[str, float],
    constraints: PlanConstraints,
    n_semesters: int,
    pinned: Mapping[str, int],
    windows: Mapping[str, tuple[int, int]] | None = None,
    critical_first: bool = False,
) -> list[list[str]] | None:
    order = {c.code: i for i, c in enumerate(schedulable)}
    load = {c.code: difficulty.get(c.code, DEFAULT_DIFFICULTY) for c in schedulable}
    by_code = {c.code: c for c in schedulable}
    pinned_at: dict[int, list[Course]] = {}
    for code, index in pinned.items():
        pinned_at.setdefault(index, []).append(by_code[code])
    windows = windows or {}
    remaining = {c.code: c for c in schedulable if c.code not in pinned}
    done = set(completed)
    semesters: list[list[str]] = []

    for s in range(n_semesters):
        left = n_semesters - s
        available = [
            c
            for c in remaining.values()
            if _satisfied(c, done) and windows.get(c.code, (0, s))[0] <= s
        ]
        chosen: list[Course] = list(pinned_at.get(s, []))
        credits = sum(course_credits(c, constraints) for c in chosen)
        total = sum(load[c.code] for c in chosen)

        def fits(course: Course, credits: int, count: int) -> bool:
            return (
                credits + course_credits(course, constraints) <= constraints.max_credits
                and count < constraints.max_courses
            )

        # A course whose semester range ends now has to go in now.
        for course in available:
            if windows.get(course.code, (0, -1))[1] == s and course not in chosen:
                chosen.append(course)
                credits += course_credits(course, constraints)
                total += load[course.code]

        # A course with a long chain behind it must start now or the plan overruns.
        urgent = sorted(
            (c for c in available if height[c.code] >= left - 1),
            key=lambda c: (-height[c.code], order[c.code]),
        )
        for course in urgent:
            if course not in chosen and fits(course, credits, len(chosen)):
                chosen.append(course)
                credits += course_credits(course, constraints)
                total += load[course.code]

        target = (
            sum(load[code] for code in remaining)
            + sum(load[code] for code, index in pinned.items() if index >= s)
        ) / left

        # Later semesters have limited room, so take at least enough now to
        # leave them a feasible amount (by course count and by credits).
        room_courses = room_credits = 0
        for k in range(s + 1, n_semesters):
            room_courses += constraints.max_courses - len(pinned_at.get(k, []))
            room_credits += constraints.max_credits - sum(
                course_credits(c, constraints) for c in pinned_at.get(k, [])
            )
        min_count = len(remaining) - room_courses
        min_credits = (
            sum(course_credits(c, constraints) for c in remaining.values()) - room_credits
        )
        while len(chosen) < min_count or credits < min_credits:
            candidates = [c for c in available if c not in chosen and fits(c, credits, len(chosen))]
            if not candidates:
                break
            course = min(
                candidates,
                key=lambda c: (
                    -height[c.code] if critical_first else 0,
                    abs(total + load[c.code] - target),
                    order[c.code],
                ),
            )
            chosen.append(course)
            credits += course_credits(course, constraints)
            total += load[course.code]

        optional = sorted(
            (c for c in available if c not in chosen),
            key=lambda c: (-height[c.code] if critical_first else 0, -load[c.code], order[c.code]),
        )
        for course in optional:
            # Packing mode takes everything that fits; the local search evens the plan out later.
            if fits(course, credits, len(chosen)) and (
                critical_first or abs(total + load[course.code] - target) < abs(total - target)
            ):
                chosen.append(course)
                credits += course_credits(course, constraints)
                total += load[course.code]

        semesters.append([c.code for c in chosen])
        done.update(c.code for c in chosen)
        for course in chosen:
            remaining.pop(course.code, None)

    return semesters if not remaining else None


def _improve(
    semesters: list[list[str]],
    schedulable: Sequence[Course],
    completed: set[str],
    difficulty: Mapping[str, float],
    constraints: PlanConstraints,
    pinned: Mapping[str, int],
    baseline: Sequence[Sequence[str]] = (),
    windows: Mapping[str, tuple[int, int]] | None = None,
) -> list[list[str]]:
    """Move or swap courses while the plan stays valid and gets more even.

    Pinned courses stay where they are. Once no move makes the plan more even, courses move back
    toward their document-order semester as long as the plan stays (nearly) as even, so
    courses with nothing to tell them apart are not scattered at random.
    """
    by_code = {c.code: c for c in schedulable}
    required = [code for sem in semesters for code in sem]
    plan = [list(sem) for sem in semesters]
    best = load_variance(plan, difficulty)

    improved = True
    while improved:
        improved = False
        for candidate in _neighbours(plan, set(pinned)):
            variance = load_variance(candidate, difficulty)
            if (
                variance < best - 1e-9
                and _in_windows(candidate, windows or {})
                and not check_plan(candidate, by_code, completed, constraints, required)
            ):
                plan, best, improved = candidate, variance, True
                break

    home = {code: i for i, sem in enumerate(baseline) for code in sem}

    def drift(candidate: Sequence[Sequence[str]]) -> int:
        return sum(abs(i - home.get(code, i)) for i, sem in enumerate(candidate) for code in sem)

    if home:
        ceiling = best + max(0.05, 0.02 * best)
        away = drift(plan)
        improved = True
        while improved:
            improved = False
            for candidate in _neighbours(plan, set(pinned)):
                closer = drift(candidate)
                if (
                    closer < away
                    and _in_windows(candidate, windows or {})
                    and load_variance(candidate, difficulty) <= ceiling
                    and not check_plan(candidate, by_code, completed, constraints, required)
                ):
                    plan, away, improved = candidate, closer, True
                    break

    while plan and not plan[-1]:
        plan.pop()
    return plan


def _in_windows(plan: Sequence[Sequence[str]], windows: Mapping[str, tuple[int, int]]) -> bool:
    for index, semester in enumerate(plan):
        for code in semester:
            first, last = windows.get(code, (0, len(plan)))
            if not first <= index <= last:
                return False
    return True


def _neighbours(plan: list[list[str]], frozen: Collection[str] = ()) -> Iterator[list[list[str]]]:
    for i, source in enumerate(plan):
        for code in source:
            if code in frozen:
                continue
            for j, target in enumerate(plan):
                if i == j:
                    continue
                moved = [list(sem) for sem in plan]
                moved[i].remove(code)
                moved[j].append(code)
                yield moved
                for other in target:
                    if other in frozen:
                        continue
                    swapped = [list(sem) for sem in plan]
                    swapped[i][swapped[i].index(code)] = other
                    swapped[j][swapped[j].index(other)] = code
                    yield swapped
