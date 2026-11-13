import pytest

from course_planner.editing import (
    add_course,
    find_course,
    move_course,
    plan_wide_issues,
    remove_course,
    summarise,
)
from course_planner.models import Course
from course_planner.planner import IssueKind, PlanConstraints, check_plan

LIMITS = PlanConstraints(max_credits=12, max_courses=2, max_semesters=6)
CATALOG = {
    "A1": Course("A1", credits=6),
    "A2": Course("A2", credits=6, prerequisites=(("A1",),)),
    "B1": Course("B1", credits=6),
}
PLAN = [["A1", "B1"], ["A2"]]


def test_move_returns_new_plan_and_leaves_input_alone():
    moved = move_course(PLAN, "B1", 1)
    assert moved == [["A1"], ["A2", "B1"]]
    assert PLAN == [["A1", "B1"], ["A2"]]


def test_move_to_new_semester_and_trims_empty_tail():
    assert move_course(PLAN, "A2", 2) == [["A1", "B1"], [], ["A2"]]
    assert move_course([["A1"], ["A2"]], "A2", 0) == [["A1", "A2"]]


def test_move_to_same_semester_is_a_no_op():
    assert move_course(PLAN, "A1", 0) == PLAN


def test_move_unknown_course_or_semester_raises():
    with pytest.raises(ValueError):
        move_course(PLAN, "ZZ", 0)
    with pytest.raises(ValueError):
        move_course(PLAN, "A1", 5)


def test_add_and_remove():
    assert add_course(PLAN, "E1", 2) == [["A1", "B1"], ["A2"], ["E1"]]
    assert remove_course([["A1"], ["E1"]], "E1") == [["A1"]]
    with pytest.raises(ValueError):
        add_course(PLAN, "E1", 9)
    with pytest.raises(ValueError):
        remove_course(PLAN, "E1")


def test_find_course():
    assert find_course(PLAN, "A2") == 1
    assert find_course(PLAN, "ZZ") is None


def test_edit_then_recheck_flags_prerequisite_break():
    broken = move_course(PLAN, "A2", 0)
    issues = check_plan(broken, CATALOG, (), LIMITS, required=CATALOG)
    kinds = {i.kind for i in issues}
    assert IssueKind.PREREQ_ORDER in kinds and IssueKind.COURSE_LIMIT in kinds


def test_summarise_attaches_problems_to_their_semester():
    broken = move_course(PLAN, "A2", 0)
    issues = check_plan(broken, CATALOG, (), LIMITS, required=CATALOG)
    summaries = summarise(broken, CATALOG, {"A1": 3.0, "A2": 4.0, "B1": 5.0}, LIMITS, issues)
    assert summaries[0].credits == 18 and summaries[0].difficulty == 12.0
    assert not summaries[0].ok
    assert plan_wide_issues(issues) == []


def test_missing_course_is_plan_wide():
    issues = check_plan([["A1"]], CATALOG, (), LIMITS, required=CATALOG)
    assert {i.kind for i in plan_wide_issues(issues)} == {IssueKind.MISSING_COURSE}


def test_summary_total_uses_the_same_default_difficulty_as_the_evenness_metric():
    from course_planner.metrics import DEFAULT_DIFFICULTY

    summary = summarise([["A1", "B1"]], CATALOG, {"A1": 2.0}, LIMITS, [])[0]
    assert summary.difficulty == round(2.0 + DEFAULT_DIFFICULTY, 2)
