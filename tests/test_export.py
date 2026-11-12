import csv
import io

from course_planner.difficulty import difficulty_score
from course_planner.export import COLUMNS, plan_to_csv
from course_planner.models import Course


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_exports_one_row_per_course_in_semester_order():
    catalog = {
        "A1": Course("A1", "Intro, Part 1", 6, assessments=3),
        "B1": Course("B1", "Next", 3),
    }
    scores = {c: difficulty_score(course) for c, course in catalog.items()}
    scores["A1"] = difficulty_score(catalog["A1"], [0.5])
    out = rows(plan_to_csv([["A1"], ["B1"]], catalog, scores, electives=["B1"]))
    assert list(out[0]) == COLUMNS
    assert [(r["Semester"], r["Course"], r["Type"]) for r in out] == [
        ("1", "A1", "Required"),
        ("2", "B1", "Elective"),
    ]
    assert out[0]["Title"] == "Intro, Part 1"
    assert out[0]["Basis"] == "Past student reviews (1)"
    assert out[1]["Basis"] == "Document only (no reviews)"


def test_formula_like_titles_are_neutralised():
    catalog = {"A1": Course("A1", "=HYPERLINK(\"http://x\")", 6)}
    assert rows(plan_to_csv([["A1"]], catalog, {}))[0]["Title"].startswith("'=")


def test_empty_plan_is_just_the_header():
    assert plan_to_csv([], {}, {}).strip() == ",".join(COLUMNS)


def test_own_rating_replaces_the_estimate_in_the_export():
    catalog = {"A1": Course("A1", "Intro", 6, assessments=3)}
    scores = {"A1": difficulty_score(catalog["A1"])}
    row = rows(plan_to_csv([["A1"]], catalog, scores, own_ratings={"A1": 9.5}))[0]
    assert row["Difficulty (1-10)"] == "9.5" and row["Basis"] == "Your own rating"
