"""Streamlit app: upload a requirement document, review the draft plan, adjust it.

Run with ``streamlit run src/course_planner/app.py``.

Accessibility choices: every control is a native Streamlit widget (keyboard
operable), status is always shown as an icon *and* a word, and errors say what
went wrong and what to try next.
"""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from course_planner.difficulty import DifficultyScore, difficulty_score
from course_planner.editing import (
    add_course,
    find_course,
    move_course,
    plan_wide_issues,
    remove_course,
    summarise,
)
from course_planner.intake import read_document
from course_planner.metrics import compare_to_baseline
from course_planner.models import Course, ParseResult
from course_planner.parser import parse_completed_courses
from course_planner.planner import PlanConstraints, check_plan, generate_plan
from course_planner.prerequisites import parse_prerequisites
from course_planner.reviews import load_dataset
from course_planner.storage import DocumentStore

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "data" / "samples" / "sample_requirements.txt"
SOURCE_UPLOAD, SOURCE_PASTE, SOURCE_SAMPLE = (
    "Upload a file",
    "Paste text",
    "Use the sample document",
)
CODE_RE = re.compile(r"^[A-Z]{4}\d{4}[A-Z]?$")
ICONS = {"success": "✅", "warning": "⚠️", "error": "❌", "info": "ℹ️"}

ss = st.session_state


# --------------------------------------------------------------------------- helpers


def notify(level: str, text: str) -> None:
    """Show a message with both an icon and a word, never colour alone."""
    label = {"success": "OK", "warning": "Warning", "error": "Problem", "info": "Note"}[level]
    getattr(st, level)(f"**{label}:** {text}", icon=ICONS[level])


def store() -> DocumentStore:
    return DocumentStore()


def current_constraints() -> PlanConstraints:
    return PlanConstraints(
        max_credits=int(ss.get("max_credits", 24)),
        max_courses=int(ss.get("max_courses", 5)),
        max_semesters=int(ss.get("max_semesters", 8)),
    )


class InputError(Exception):
    """A problem with what the student provided, worded for them."""


def read_source() -> tuple[bytes, str]:
    source = ss.get("source", SOURCE_SAMPLE)
    if source == SOURCE_SAMPLE:
        if not SAMPLE_PATH.exists():
            raise InputError("The sample document is missing. Try uploading a file instead.")
        return SAMPLE_PATH.read_bytes(), SAMPLE_PATH.name
    if source == SOURCE_PASTE:
        text = ss.get("pasted", "")
        if not text.strip():
            raise InputError("Paste your requirement text into the box first.")
        return text.encode("utf-8"), "pasted.txt"
    uploaded = ss.get("upload")
    if uploaded is None:
        raise InputError("Choose a PDF, text or CSV file to upload first.")
    return uploaded.getvalue(), uploaded.name


# --------------------------------------------------------------------------- callbacks


def build_plan() -> None:
    ss.pop("flash", None)
    try:
        data, name = read_source()
    except InputError as exc:
        ss.notices = [("error", str(exc))]
        ss.pop("gen", None)
        return

    parsed, notices = read_document(data, name, store())
    ss.notices = notices
    if parsed is None:
        ss.pop("gen", None)
        return
    notices.extend(("warning", w) for w in parsed.warnings)

    completed = parse_completed_courses(ss.get("completed_text", ""))
    known = {c.code for c in parsed.courses}
    unknown = sorted(completed - known)
    if unknown:
        notices.append(
            (
                "info",
                f"Completed courses not in the document (kept as completed): {', '.join(unknown)}.",
            )
        )

    review_data = load_dataset()
    if review_data.reviews:
        covered = sum(1 for c in parsed.courses if c.code in review_data.sentiments)
        notices.append(
            (
                "info",
                f"Loaded {len(review_data.reviews)} review(s) covering {covered} of your "
                "courses from the local dataset.",
            )
        )
        if review_data.excluded:
            notices.append(
                (
                    "warning",
                    f"{review_data.excluded} review(s) were left out of the difficulty score "
                    "(not translated or no rating).",
                )
            )
    else:
        notices.append(
            (
                "info",
                "No local review dataset was found, so difficulty uses the requirement "
                "document only.",
            )
        )

    scores = {
        c.code: difficulty_score(c, review_data.sentiments.get(c.code, ()))
        for c in parsed.courses
    }
    difficulty = {code: s.score for code, s in scores.items()}
    gen = generate_plan(parsed.courses, completed, difficulty, current_constraints())

    ss.parsed, ss.completed, ss.scores, ss.difficulty = parsed, completed, scores, difficulty
    ss.gen, ss.semesters, ss.electives = gen, [list(s) for s in gen.semesters], {}
    ss.review_count = len(review_data.reviews)


def reset_plan() -> None:
    ss.semesters = [list(s) for s in ss.gen.semesters]
    ss.electives = {}
    ss.flash = ("info", "Plan reset to the suggested plan.")


def move_selected() -> None:
    code, target = ss.get("move_code"), ss.get("move_target")
    if code is None or target is None:
        return
    if find_course(ss.semesters, code) == target:
        ss.flash = ("info", f"{code} is already in semester {target + 1}.")
        return
    ss.semesters = move_course(ss.semesters, code, target)
    ss.flash = (
        "info",
        f"Moved {code} to semester {find_course(ss.semesters, code) + 1}. See the re-check below.",
    )


def add_elective() -> None:
    code = ss.get("el_code", "").strip().upper()
    if not CODE_RE.match(code):
        ss.flash = ("error", "Enter a course code like ARTS1234 (four letters, four digits).")
        return
    if code in {c.code for c in ss.parsed.courses} or code in ss.electives or code in ss.completed:
        ss.flash = (
            "error",
            f"{code} is already in your requirements, electives or completed list.",
        )
        return
    course = Course(
        code=code,
        title=ss.get("el_title", "").strip() or "Elective",
        credits=int(ss.get("el_credits", 6)),
        prerequisites=parse_prerequisites(ss.get("el_prereq", "")),
        assessments=int(ss.get("el_assess", 0)) or None,
    )
    ss.electives[code] = course
    score = difficulty_score(course)
    ss.scores[code], ss.difficulty[code] = score, score.score
    ss.semesters = add_course(ss.semesters, code, ss.get("el_target", 0))
    ss.flash = ("info", f"Added elective {code}. See the re-check below.")


def remove_elective() -> None:
    code = ss.get("el_remove")
    if code in ss.electives:
        ss.semesters = remove_course(ss.semesters, code)
        del ss.electives[code]
        ss.flash = ("info", f"Removed elective {code}.")


def delete_saved() -> None:
    removed = store().delete_all()
    ss.sidebar_flash = f"Deleted {removed} saved document(s) from this computer."


# --------------------------------------------------------------------------- rendering


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Semester limits")
        st.number_input("Max credits per semester", 1, 60, 24, key="max_credits")
        st.number_input("Max courses per semester", 1, 12, 5, key="max_courses")
        st.number_input("Max number of semesters", 1, 16, 8, key="max_semesters")
        st.caption("Changing a limit re-checks your plan. Use 'Build my plan' to regenerate it.")

        st.header("Your data")
        st.caption("Nothing you upload leaves this computer.")
        count = len(store().list_documents())
        st.write(f"Saved documents: {count}")
        st.button("Delete all saved documents", on_click=delete_saved, disabled=count == 0)
        if message := ss.pop("sidebar_flash", None):
            notify("success", message)


def render_input() -> None:
    st.subheader("1. Your requirement document")
    st.radio(
        "How do you want to provide it?", [SOURCE_SAMPLE, SOURCE_UPLOAD, SOURCE_PASTE], key="source"
    )
    source = ss.get("source", SOURCE_SAMPLE)
    if source == SOURCE_UPLOAD:
        st.file_uploader("PDF, plain text or CSV", type=["pdf", "txt", "csv"], key="upload")
    elif source == SOURCE_PASTE:
        st.text_area("Paste the requirement text", height=200, key="pasted")
    else:
        st.caption(
            "A short fictional Computer Science programme, so you can try the app right away."
        )
    st.text_area(
        "Courses you have already completed (optional)",
        placeholder="e.g. COMP1117, MATH1013",
        key="completed_text",
        height=80,
    )
    st.button("Build my plan", type="primary", on_click=build_plan)


def render_notices() -> None:
    for level, text in ss.get("notices", []):
        notify(level, text)


def render_results(constraints: PlanConstraints) -> None:
    parsed: ParseResult = ss.parsed
    gen = ss.gen
    catalog = {c.code: c for c in parsed.courses} | ss.electives
    required = [c.code for c in parsed.courses if c.code not in ss.completed]
    blocked = set(gen.unscheduled)
    issues = check_plan(
        ss.semesters,
        catalog,
        ss.completed,
        constraints,
        required=[code for code in required if code not in blocked],
    )

    st.subheader("2. Your draft plan")
    review_basis = (
        f" and {ss.get('review_count', 0)} student review(s) from the local dataset"
        if ss.get("review_count", 0)
        else " only (credits and number of assessments); no student reviews are loaded yet"
    )
    st.caption(
        "A draft to review, not an official graduation audit. Difficulty is an estimate from "
        f"the requirement document{review_basis}. It is not an official HKU rating."
    )
    if flash := ss.pop("flash", None):
        notify(*flash)

    if not issues and not gen.unscheduled:
        notify(
            "success",
            "Every required course is scheduled once, in prerequisite order, within your limits.",
        )
    if gen.unscheduled or gen.issues:
        notify(
            "error",
            f"{len(gen.unscheduled)} course(s) could not be scheduled: "
            f"{', '.join(gen.unscheduled)}.",
        )
        for issue in gen.issues:
            st.markdown(f"- ❌ **Problem:** {issue.message}")
    if issues:
        notify("error", f"The plan currently has {len(issues)} problem(s) to fix.")
        for issue in plan_wide_issues(issues):
            st.markdown(f"- ❌ **Problem:** {issue.message}")

    summaries = summarise(ss.semesters, catalog, ss.difficulty, constraints, issues)
    for summary in summaries:
        status = "✅ OK" if summary.ok else f"❌ {len(summary.problems)} problem(s)"
        with st.container(border=True):
            st.markdown(
                f"#### Semester {summary.index + 1} · {status}\n"
                f"{summary.credits} credits · {summary.course_count} course(s) · "
                f"total difficulty {summary.difficulty}"
            )
            st.table(course_rows(ss.semesters[summary.index], catalog))
            for issue in summary.problems:
                st.markdown(f"- ❌ **Problem:** {issue.message}")
    if not summaries:
        st.write("No courses are scheduled.")

    render_evenness()
    render_adjust(catalog, constraints)


def course_rows(codes: list[str], catalog: dict[str, Course]) -> list[dict[str, str]]:
    rows = []
    for code in codes:
        course = catalog.get(code)
        score: DifficultyScore | None = ss.scores.get(code)
        basis = "—"
        if score is not None:
            basis = (
                "ℹ️ Document only (no reviews)"
                if score.review_free
                else f"Past student reviews ({score.review_count})"
            )
            if score.used_defaults:
                basis += "; missing details estimated"
        rows.append(
            {
                "Course": code,
                "Title": course.title if course else "",
                "Credits": str(course.credits) if course and course.credits is not None else "?",
                "Difficulty (1-10)": f"{score.score:.1f}" if score else "?",
                "Basis": basis,
                "Type": "Elective" if code in ss.electives else "Required",
            }
        )
    return rows


def render_evenness() -> None:
    required = {c.code for c in ss.parsed.courses}
    mine = [[c for c in sem if c in required] for sem in ss.semesters]
    comparison = compare_to_baseline(mine, ss.gen.baseline, ss.difficulty)
    verdict = "✅ more even than" if comparison.more_even else "ℹ️ not more even than"
    st.markdown(
        f"**Difficulty spread** (variance of each semester's total difficulty, lower is more even; "
        f"required courses only): your plan {comparison.plan_variance:.2f} — {verdict} "
        f"taking courses in document order ({comparison.baseline_variance:.2f})."
    )


def render_adjust(catalog: dict[str, Course], constraints: PlanConstraints) -> None:
    st.subheader("3. Adjust your plan")
    st.caption("Every change is re-checked straight away. Problems are shown above, not blocked.")
    planned = [code for sem in ss.semesters for code in sem]
    n = len(ss.semesters)
    course_labels = {
        code: f"{code} · {catalog[code].title} (now semester {find_course(ss.semesters, code) + 1})"
        for code in planned
    }

    with st.form("move_form"):
        st.markdown("**Move a course to another semester**")
        st.selectbox(
            "Course",
            planned,
            key="move_code",
            format_func=course_labels.__getitem__,
        )
        st.selectbox(
            "Move to",
            list(range(n + 1)),
            key="move_target",
            format_func=lambda i: f"Semester {i + 1}" if i < n else f"New semester ({n + 1})",
        )
        st.form_submit_button("Move course", on_click=move_selected)

    with st.form("elective_form"):
        st.markdown("**Add an elective**")
        left, right = st.columns(2)
        left.text_input("Course code", key="el_code", placeholder="ARTS1234")
        right.text_input("Title (optional)", key="el_title")
        left.number_input("Credits", 1, 12, 6, key="el_credits")
        right.number_input("Number of graded assessments (0 if unknown)", 0, 20, 0, key="el_assess")
        st.text_input(
            "Prerequisites (optional)",
            key="el_prereq",
            placeholder="COMP1117 and (MATH1013 or MATH1853)",
        )
        st.selectbox(
            "Place in",
            list(range(n + 1)),
            key="el_target",
            format_func=lambda i: f"Semester {i + 1}" if i < n else f"New semester ({n + 1})",
        )
        st.form_submit_button("Add elective", on_click=add_elective)

    if ss.electives:
        with st.form("remove_form"):
            st.selectbox("Remove an elective", list(ss.electives), key="el_remove")
            st.form_submit_button("Remove elective", on_click=remove_elective)

    st.button("Reset to the suggested plan", on_click=reset_plan)


def main() -> None:
    st.set_page_config(page_title="HKU Course Planner", page_icon="📚", layout="wide")
    st.title("HKU Course Planner")
    st.write(
        "Turn your programme's requirement document into a semester-by-semester draft plan. "
        "It does not certify graduation or replace your academic adviser, and it is not meant "
        "for double majors, transfer credit or requirement waivers."
    )
    render_sidebar()
    render_input()
    render_notices()
    if "gen" in ss:
        render_results(current_constraints())


main()
