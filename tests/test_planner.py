import pytest

from course_planner.metrics import compare_to_baseline, load_variance, semester_loads
from course_planner.models import Course
from course_planner.planner import (
    IssueKind,
    PlanConstraints,
    baseline_plan,
    check_plan,
    generate_plan,
)


def course(code, *prereqs, credits=6):
    return Course(code, credits=credits, prerequisites=tuple(tuple(p.split("|")) for p in prereqs))


def kinds(issues):
    return [issue.kind for issue in issues]


LIMITS = PlanConstraints(max_credits=12, max_courses=2, max_semesters=6)


# ------------------------------------------------------------------ generation


def test_plan_respects_prerequisites_and_limits():
    courses = [
        course("A1"),
        course("A2", "A1"),
        course("A3", "A2"),
        course("B1"),
        course("B2", "B1"),
        course("C1"),
    ]
    result = generate_plan(courses, constraints=LIMITS)
    assert result.ok
    catalog = {c.code: c for c in courses}
    assert check_plan(result.semesters, catalog, (), LIMITS, required=catalog) == []
    assert sorted(code for sem in result.semesters for code in sem) == sorted(catalog)
    assert len(result.semesters) == 3  # A1 -> A2 -> A3 is the critical path


def test_completed_courses_are_removed_and_unlock_others():
    courses = [course("A1"), course("A2", "A1"), course("A3", "A2")]
    result = generate_plan(courses, completed={"A1"}, constraints=LIMITS)
    assert result.ok
    assert result.semesters == [["A2"], ["A3"]]


def test_or_group_is_satisfied_by_either_course():
    courses = [course("A1"), course("B1"), course("C1", "A1|B1")]
    result = generate_plan(courses, constraints=PlanConstraints(max_courses=3, max_credits=24))
    assert result.ok
    assert result.semesters[-1] == ["C1"] or "C1" in result.semesters[1]


def test_or_group_satisfied_by_completed_course_only():
    result = generate_plan([course("C1", "A1|B1")], completed={"B1"}, constraints=LIMITS)
    assert result.ok and result.semesters == [["C1"]]


def test_empty_requirements_give_empty_plan():
    result = generate_plan([], constraints=LIMITS)
    assert result.ok and result.semesters == [] and result.baseline == []


def test_duplicate_course_entries_are_planned_once():
    result = generate_plan([course("A1"), course("A1")], constraints=LIMITS)
    assert result.semesters == [["A1"]]


def test_missing_credits_use_default():
    constraints = PlanConstraints(max_credits=12, max_courses=5, default_credits=6)
    courses = [Course("A1"), Course("A2"), Course("A3")]
    result = generate_plan(courses, constraints=constraints)
    assert result.ok and len(result.semesters) == 2  # 3 x 6 credits > 12


# ------------------------------------------------------------------ fail-safe


def test_circular_prerequisite_is_flagged_not_dropped():
    courses = [course("A1"), course("B1", "C1"), course("C1", "B1"), course("D1", "C1")]
    result = generate_plan(courses, constraints=LIMITS)
    assert not result.ok
    assert result.semesters == [["A1"]]
    assert result.unscheduled == ["B1", "C1", "D1"]
    cycle = next(i for i in result.issues if i.kind is IssueKind.CYCLE)
    assert cycle.courses == ("B1", "C1")
    assert "Circular prerequisite" in cycle.message
    blocked = next(i for i in result.issues if i.kind is IssueKind.BLOCKED)
    assert blocked.courses == ("D1",)


def test_self_prerequisite_is_a_cycle():
    result = generate_plan([course("A1", "A1")], constraints=LIMITS)
    assert kinds(result.issues) == [IssueKind.CYCLE]
    assert result.unscheduled == ["A1"] and result.semesters == []


def test_cycle_through_or_group_that_has_an_escape_is_not_a_cycle():
    # A1 needs B1 or X1; X1 is free, so A1 and B1 are both schedulable.
    courses = [course("A1", "B1|X1"), course("B1", "A1"), course("X1")]
    result = generate_plan(courses, constraints=LIMITS)
    assert result.ok
    assert result.semesters[0] == ["X1"]


def test_prerequisite_missing_from_document_is_flagged():
    result = generate_plan([course("A1", "ZZZZ9999"), course("A2", "A1")], constraints=LIMITS)
    assert result.semesters == []
    assert result.unscheduled == ["A1", "A2"]
    missing = next(i for i in result.issues if i.kind is IssueKind.MISSING_PREREQUISITE)
    assert missing.courses == ("A1",) and "ZZZZ9999" in missing.message
    assert IssueKind.BLOCKED in kinds(result.issues)


def test_course_larger_than_credit_limit_is_flagged():
    result = generate_plan([course("A1", credits=30), course("A2", "A1")], constraints=LIMITS)
    assert IssueKind.TOO_LARGE in kinds(result.issues)
    assert result.unscheduled == ["A1", "A2"]


def test_prerequisite_chain_longer_than_semester_limit_is_flagged():
    chain = [course("A1"), course("A2", "A1"), course("A3", "A2"), course("A4", "A3")]
    result = generate_plan(chain, constraints=PlanConstraints(12, 2, max_semesters=3))
    assert result.semesters == [["A1"], ["A2"], ["A3"]]
    assert result.unscheduled == ["A4"]
    assert kinds(result.issues) == [IssueKind.NO_ROOM]


def test_load_limit_pushing_past_semester_limit_is_flagged():
    courses = [course(f"C{i}") for i in range(5)]
    result = generate_plan(courses, constraints=PlanConstraints(12, 2, max_semesters=2))
    assert sum(len(s) for s in result.semesters) == 4
    assert len(result.unscheduled) == 1
    assert kinds(result.issues) == [IssueKind.NO_ROOM]


def test_planner_never_returns_an_invalid_plan():
    courses = [course("A1", "B1"), course("B1", "A1"), course("C1"), course("C2", "C1")]
    result = generate_plan(courses, constraints=LIMITS)
    catalog = {c.code: c for c in courses}
    assert check_plan(result.semesters, catalog, (), LIMITS) == []


# ------------------------------------------------------------------ balancing


def test_balanced_plan_is_more_even_than_document_order():
    # Document order front-loads the three hard courses; balancing mixes them.
    courses = [
        course("H1", credits=6),
        course("H2", credits=6),
        course("H3", credits=6),
        course("E1", credits=6),
        course("E2", credits=6),
        course("E3", credits=6),
    ]
    difficulty = {"H1": 9, "H2": 9, "H3": 9, "E1": 2, "E2": 2, "E3": 2}
    constraints = PlanConstraints(max_credits=18, max_courses=3, max_semesters=4)
    result = generate_plan(courses, difficulty=difficulty, constraints=constraints)
    comparison = compare_to_baseline(result.semesters, result.baseline, difficulty)
    assert result.baseline == [["H1", "H2", "H3"], ["E1", "E2", "E3"]]
    assert comparison.more_even
    assert comparison.plan_variance == pytest.approx(12.25)  # loads 20 and 13, the best split
    assert len(result.semesters) == 2


def test_plan_is_never_longer_than_baseline():
    courses = [course(f"A{i}", *( [f"A{i - 1}"] if i else [])) for i in range(4)]
    courses += [course(f"B{i}") for i in range(4)]
    result = generate_plan(courses, constraints=PlanConstraints(18, 3, 8))
    assert len(result.semesters) <= len(result.baseline)


# ------------------------------------------------------------------ metrics


def test_semester_loads_and_variance():
    difficulty = {"A": 2.0, "B": 4.0, "C": 6.0}
    assert semester_loads([["A", "B"], ["C"]], difficulty) == [6.0, 6.0]
    assert load_variance([["A", "B"], ["C"]], difficulty) == 0.0
    assert load_variance([["A"], ["B"], ["C"]], difficulty) == pytest.approx(8 / 3)
    assert load_variance([], difficulty) == 0.0


def test_unknown_difficulty_uses_default():
    assert semester_loads([["Z"]], {}) == [5.5]


def test_equal_variance_is_not_better():
    assert not compare_to_baseline([["A"]], [["A"]], {"A": 1.0}).more_even


# ------------------------------------------------------------------ check_plan


CATALOG = {c.code: c for c in [course("A1"), course("A2", "A1"), course("B1", "A1|A2")]}


def test_check_plan_accepts_valid_plan():
    assert check_plan([["A1"], ["A2", "B1"]], CATALOG, (), LIMITS, required=CATALOG) == []


def test_check_plan_flags_prerequisite_in_same_or_later_semester():
    same = check_plan([["A1", "A2"]], CATALOG, (), LIMITS)
    later = check_plan([["A2"], ["A1"]], CATALOG, (), LIMITS)
    assert kinds(same) == [IssueKind.PREREQ_ORDER]
    assert kinds(later) == [IssueKind.PREREQ_ORDER]
    assert later[0].semester == 0 and "semester 1" in later[0].message


def test_check_plan_flags_duplicates_missing_and_unknown():
    issues = check_plan([["A1", "A1"], ["ZZZZ1"]], CATALOG, (), LIMITS, required=["A1", "A2"])
    assert set(kinds(issues)) == {
        IssueKind.DUPLICATE,
        IssueKind.UNKNOWN_COURSE,
        IssueKind.MISSING_COURSE,
    }


def test_check_plan_flags_load_limits():
    tight = PlanConstraints(max_credits=6, max_courses=1)
    issues = check_plan([["A1", "B1"]], CATALOG, {"A2"}, tight)
    assert IssueKind.CREDIT_LIMIT in kinds(issues)
    assert IssueKind.COURSE_LIMIT in kinds(issues)


def test_check_plan_uses_completed_courses():
    assert check_plan([["A2"]], CATALOG, {"A1"}, LIMITS) == []


def test_constraints_validate_inputs():
    with pytest.raises(ValueError):
        PlanConstraints(max_credits=0)


def test_baseline_takes_courses_in_document_order():
    courses = [course("A1"), course("A2", "A1"), course("B1"), course("C1")]
    semesters, leftover = baseline_plan(courses, (), LIMITS)
    assert semesters == [["A1", "B1"], ["A2", "C1"]] and leftover == []
