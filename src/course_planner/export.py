"""Export the (possibly hand-adjusted) plan as CSV, a should-have in the proposal."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence

from course_planner.difficulty import DifficultyScore
from course_planner.models import Course

COLUMNS = ["Semester", "Course", "Title", "Credits", "Difficulty (1-10)", "Basis", "Type"]


def _safe(value: str) -> str:
    """Stop spreadsheet apps from running text taken from an uploaded document as a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def plan_to_csv(
    semesters: Sequence[Sequence[str]],
    catalog: Mapping[str, Course],
    scores: Mapping[str, DifficultyScore],
    electives: Sequence[str] = (),
    own_ratings: Mapping[str, float] | None = None,
) -> str:
    """One row per planned course, in semester order.

    ``own_ratings`` are the student's self-reported 1-10 ratings; they replace the estimate.
    """
    own_ratings = own_ratings or {}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for number, codes in enumerate(semesters, start=1):
        for code in codes:
            course = catalog.get(code)
            score = scores.get(code)
            basis = ""
            own = own_ratings.get(code)
            if own is not None:
                basis = "Your own rating"
            elif score is not None:
                basis = (
                    "Document only (no reviews)"
                    if score.review_free
                    else f"Past student reviews ({score.review_count})"
                )
            writer.writerow(
                [
                    number,
                    code,
                    _safe(course.title) if course else "",
                    course.credits if course and course.credits is not None else "",
                    f"{own:.1f}" if own is not None else f"{score.score:.1f}" if score else "",
                    basis,
                    "Elective" if code in electives else "Required",
                ]
            )
    return out.getvalue()
