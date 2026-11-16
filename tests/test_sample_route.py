"""The 8-semester computer science route that the project webpage shows."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from course_planner.parser import parse_text

ROOT = Path(__file__).resolve().parents[1]
ROUTE = ROOT / "data" / "samples" / "cs_route_8_semesters.txt"


def _load_builder():
    path = ROOT / "docs" / "build_plan_data.py"
    spec = importlib.util.spec_from_file_location("build_plan_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


def test_route_document_parses_without_warnings_and_every_course_is_required():
    parsed = parse_text(ROUTE.read_text(encoding="utf-8"))
    assert len(parsed.courses) == 25
    assert parsed.warnings == []
    assert not any(course.elective for course in parsed.courses)


def test_route_meets_every_credit_requirement_of_the_programme():
    data = builder.build()
    assert sum(course["credits"] for course in data["courses"]) == 240
    for group in data["groups"]:
        credits = sum(c["credits"] for c in data["courses"] if c["group"] == group["id"])
        assert credits == group["needed"], group["name"]


def test_route_plans_into_eight_full_legal_semesters():
    data = builder.build()
    by_code = {course["code"]: course for course in data["courses"]}
    assert data["ok"]
    assert len(data["plan"]) == 8
    for semester in data["plan"]:
        assert sum(by_code[code]["credits"] for code in semester) == 30
    placed = [code for semester in data["plan"] for code in semester]
    assert sorted(placed) == sorted(by_code)


def test_plan_is_never_less_even_than_document_order():
    data = builder.build()
    assert data["variance"]["plan"] <= data["variance"]["baseline"]
