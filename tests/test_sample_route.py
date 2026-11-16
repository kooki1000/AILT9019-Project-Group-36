"""The 8-semester computer science route that the project webpage shows."""

from __future__ import annotations

from pathlib import Path

from course_planner.difficulty import difficulty_score
from course_planner.parser import parse_text
from course_planner.planner import PlanConstraints, check_plan, generate_plan

ROUTE = Path(__file__).resolve().parents[1] / "data" / "samples" / "cs_route_8_semesters.txt"
LIMITS = PlanConstraints(max_credits=36, max_courses=5, max_semesters=8)


def test_route_parses_without_warnings_and_every_course_is_required():
    parsed = parse_text(ROUTE.read_text(encoding="utf-8"))
    assert len(parsed.courses) == 40
    assert parsed.warnings == []
    assert not any(course.elective for course in parsed.courses)


def test_route_plans_into_eight_full_legal_semesters():
    parsed = parse_text(ROUTE.read_text(encoding="utf-8"))
    scores = {c.code: difficulty_score(c).score for c in parsed.courses}
    result = generate_plan(parsed.courses, (), scores, LIMITS)
    assert result.ok
    assert [len(semester) for semester in result.semesters] == [5] * 8
    assert check_plan(result.semesters, {c.code: c for c in parsed.courses}, (), LIMITS) == []
