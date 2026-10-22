from pathlib import Path

import pytest

from course_planner.evaluation import (
    SuiteEvaluation,
    evaluate_case,
    evaluate_directory,
    main,
)
from course_planner.models import Course
from course_planner.parser import parse_document
from course_planner.planner import PlanConstraints

FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
EXPECTED_COURSES = {
    "case1_minor_6_courses": 6,
    "case2_major_10_courses": 10,
    "case3_business_14_courses": 14,
    "case4_cs_18_courses_alternatives": 18,
    "case5_arts_24_courses_deep_chain": 24,
}


@pytest.mark.parametrize(("name", "count"), EXPECTED_COURSES.items())
def test_constructed_documents_parse_completely(name, count):
    result = parse_document(FIXTURES / f"{name}.txt")
    assert len(result.courses) == count
    assert result.warnings == []
    assert all(c.credits and c.assessments for c in result.courses)


def test_constructed_suite_meets_the_proposal_thresholds():
    suite = evaluate_directory(FIXTURES)
    assert len(suite.cases) == 5
    assert suite.checks_passing >= 4, suite.report()
    assert suite.more_even_count >= 4, suite.report()
    assert suite.passed


def test_every_constructed_plan_passes_all_three_checks():
    for case in evaluate_directory(FIXTURES).cases:
        assert case.checks_passed, case.issues


def test_cycle_document_fails_loudly_rather_than_passing():
    courses = [
        Course("A1", credits=6),
        Course("B1", credits=6, prerequisites=(("C1",),)),
        Course("C1", credits=6, prerequisites=(("B1",),)),
    ]
    case = evaluate_case("cycle", courses)
    assert not case.checks_passed
    assert any("Circular prerequisite" in issue.message for issue in case.issues)


def test_completed_courses_are_not_required():
    courses = [Course("A1", credits=6), Course("A2", credits=6, prerequisites=(("A1",),))]
    case = evaluate_case("done", courses, completed={"A1"}, constraints=PlanConstraints())
    assert case.checks_passed and case.semesters == 1


def test_suite_needs_threshold_on_both_criteria():
    only = evaluate_case("one course", [Course("A1", credits=6)])
    suite = SuiteEvaluation((only,), threshold=1)
    assert suite.checks_passing == 1
    assert not suite.passed  # one course: plan is no more even than the baseline


def test_report_and_cli(capsys):
    assert main([str(FIXTURES)]) == 0
    output = capsys.readouterr().out
    assert "PASS" in output and "case5_arts_24_courses_deep_chain" in output
    assert main([]) == 2
