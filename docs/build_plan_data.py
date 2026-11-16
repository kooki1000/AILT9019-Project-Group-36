"""Write docs/plan-data.js: the real run that the project page's board shows.

The page's interactive plan is not mocked up. This script runs the same code the app runs
(parser, difficulty score, planner) on data/samples/cs_route_8_semesters.txt, a computer
science route modelled on HKU's BEng (Computer Science) mock study plan, and writes the result
as a small JS file the page loads. Scores come from the document alone (no reviews).

The app reads courses by course code. The mock study plan also has slots with no code (Common
Core, Chinese language, free electives), so this script adds those as 6-credit courses with
nothing known about them, which the scoring treats as mid-range. They are marked ``generic``.

    python docs/build_plan_data.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from course_planner.difficulty import difficulty_score  # noqa: E402
from course_planner.metrics import load_variance  # noqa: E402
from course_planner.models import Course  # noqa: E402
from course_planner.parser import parse_text  # noqa: E402
from course_planner.planner import PlanConstraints, generate_plan  # noqa: E402

ROUTE = ROOT / "data" / "samples" / "cs_route_8_semesters.txt"
# Eight semesters of 30 credits (240 in all) and at most 5 courses. The 12-credit final year
# project takes two slots, so its semester has four tiles.
ROUTE_LIMITS = PlanConstraints(max_credits=30, max_courses=5, max_semesters=8)

# Credits each group must reach, from the mock study plan.
CATEGORIES = [
    ("foundation", "Foundation courses", 36),
    ("core", "Disciplinary core courses", 54),
    ("capstone", "Capstone experience", 12),
    ("elective", "Disciplinary electives", 42),
    ("free", "Free electives", 42),
    ("common", "Common Core, English and digital literacy", 54),
]
# Section headings in the route document, in the order they appear there.
HEADINGS = {
    "Foundation courses": "foundation",
    "Disciplinary core courses": "core",
    "Capstone experience": "capstone",
    "Disciplinary courses for this route": "elective",
    "English and digital literacy": "common",
}
# The mock study plan read top to bottom, one semester at a time. This is the "document order"
# the plan is compared with. A name with no course code is a slot with nothing known about it
# (Common Core, Chinese language, free elective); "Disciplinary elective" slots take the route's
# chosen electives in the order they are listed in the route document.
SLOTS = [
    "COMP1117", "MATH1013", "AILT1001", "Common Core", "Common Core",
    "COMP1110", "COMP2113", "MATH2012", "Common Core", "Common Core",
    "MATH2014", "COMP2120", "COMP2119", "Common Core", "Free Elective",
    "COMP2121", "SDST2601", "COMP3314", "COMP3297", "Common Core",
    "COMP3230", "COMP3251", "COMP3278", "Disciplinary elective", "Free Elective",
    "Disciplinary elective", "Disciplinary elective", "Disciplinary elective",
    "Chinese Language", "Free Elective",
    "COMP4801", "CAES9542", "Disciplinary elective", "Free Elective", "Free Elective",
    "Disciplinary elective", "Disciplinary elective", "Free Elective", "Free Elective",
]
GENERIC = {
    "Common Core": ("common", "Any Common Core course"),
    "Chinese Language": ("common", "Chinese language enhancement"),
    "Free Elective": ("free", "Any course you like"),
}


def categories_by_code(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if line in HEADINGS:
            current = HEADINGS[line]
        elif current and re.match(r"[A-Z]{4}\d{4}\b", line):
            found[line[:8]] = current
    return found


def build(path: Path = ROUTE, constraints: PlanConstraints = ROUTE_LIMITS) -> dict:
    text = path.read_text(encoding="utf-8")
    parsed = parse_text(text)
    group_of = categories_by_code(text)
    by_code = {c.code: c for c in parsed.courses}
    electives = [c.code for c in parsed.courses if group_of[c.code] == "elective"]
    entries = []  # (course, group, label, hint, generic), in the order of SLOTS
    counts: dict[str, int] = {}
    for slot in SLOTS:
        if slot == "Disciplinary elective":
            slot = electives.pop(0)
        if slot in by_code:
            course = by_code[slot]
            entries.append((course, group_of[slot], course.code, course.title, False))
        else:
            group, hint = GENERIC[slot]
            counts[slot] = counts.get(slot, 0) + 1
            course = Course(f"{slot} {counts[slot]}", hint, 6, (), None)
            entries.append((course, group, slot, hint, True))

    courses = [e[0] for e in entries]
    difficulty = {c.code: difficulty_score(c).score for c in courses}
    result = generate_plan(courses, (), difficulty, constraints)
    return {
        "limits": {"credits": constraints.max_credits, "courses": constraints.max_courses},
        "groups": [{"id": g, "name": n, "needed": need} for g, n, need in CATEGORIES],
        "courses": [
            {
                "code": c.code,
                "label": label,
                "title": hint,
                "credits": c.credits,
                "prerequisites": [list(group) for group in c.prerequisites],
                "difficulty": difficulty[c.code],
                "group": group,
                "generic": generic,
            }
            for c, group, label, hint, generic in entries
        ],
        "plan": result.semesters,
        "baseline": result.baseline,
        "ok": result.ok,
        "variance": {
            "plan": round(load_variance(result.semesters, difficulty), 2),
            "baseline": round(load_variance(result.baseline, difficulty), 2),
        },
    }


if __name__ == "__main__":
    out = ROOT / "docs" / "plan-data.js"
    out.write_text(
        "// Generated by docs/build_plan_data.py from a real run of the app's code. Do not edit.\n"
        "window.ROUTE_RUN = " + json.dumps(build(), separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {out.relative_to(ROOT)}")
