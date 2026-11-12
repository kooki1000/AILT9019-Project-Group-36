"""End-to-end tests of the Streamlit app using Streamlit's own test harness."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).parent.parent / "src" / "course_planner" / "app.py"
REVIEWS_SAMPLE = Path(__file__).parent.parent / "data" / "reviews" / "sample_reviews.csv"


@pytest.fixture
def app(tmp_path, monkeypatch) -> AppTest:
    monkeypatch.setenv("COURSE_PLANNER_DB", str(tmp_path / "app.sqlite3"))
    # Isolate the review dataset: these tests cover the document-only path;
    # test_reviews_are_loaded_into_the_score points the app at the sample data.
    monkeypatch.setenv("COURSE_PLANNER_REVIEWS", str(tmp_path / "no_reviews.csv"))
    return AppTest.from_file(str(APP), default_timeout=30).run()


def click(at: AppTest, label: str) -> AppTest:
    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button labelled {label!r}; have {[b.label for b in at.button]}"
    return matches[0].click().run()


def text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown]
    parts += [e.value for e in at.error] + [w.value for w in at.warning]
    parts += [s.value for s in at.success] + [i.value for i in at.info]
    return "\n".join(parts)


def plan(at: AppTest) -> list[list[str]]:
    return [[row["Course"] for _, row in t.value.iterrows()] for t in at.table]


@pytest.fixture
def built(app) -> AppTest:
    at = click(app, "Build my plan")
    assert not at.exception
    return at


def test_starts_with_inputs_only(app):
    assert not app.exception
    assert [b.label for b in app.button][0] == "Build my plan"
    assert not app.table


def test_sample_document_builds_a_valid_plan(built):
    assert "Every required course is scheduled once" in text(built)
    assert sorted(c for sem in plan(built) for c in sem) == sorted(
        ["COMP1117", "COMP2113", "COMP2119", "COMP3230", "COMP3314", "MATH1013", "STAT2601"]
    )
    # Status is words plus an icon, not colour alone.
    assert "Semester 1 · ✅ OK" in text(built)
    assert "no reviews" in built.table[0].value["Basis"].iloc[0]


def test_moving_a_course_against_its_prerequisite_is_flagged(built):
    built.selectbox(key="move_code").set_value("COMP2113")
    built.selectbox(key="move_target").set_value(0)
    built = click(built, "Move course")
    assert "COMP2113" in plan(built)[0]
    body = text(built)
    assert "COMP2113 (semester 1) needs COMP1117 completed in an earlier semester" in body
    assert "problem(s) to fix" in body
    assert "❌" in body


def test_moving_back_clears_the_problem(built):
    built.selectbox(key="move_code").set_value("COMP2113")
    built.selectbox(key="move_target").set_value(0)
    built = click(built, "Move course")
    built = click(built, "Reset to the suggested plan")
    assert "Every required course is scheduled once" in text(built)
    assert "Plan reset" in text(built)


def test_move_to_new_semester_opens_one(built):
    count = len(plan(built))
    code = plan(built)[-1][0]
    built.selectbox(key="move_code").set_value(code)
    built.selectbox(key="move_target").set_value(count)
    built = click(built, "Move course")
    assert len(plan(built)) == count + 1
    assert plan(built)[-1] == [code]


def test_lowering_the_limit_rechecks_the_existing_plan(built):
    built.number_input(key="max_courses").set_value(1).run()
    body = text(built)
    assert "has 2 courses; the limit is 1" in body or "has 3 courses; the limit is 1" in body


def test_adding_a_valid_elective(built):
    built.text_input(key="el_code").set_value("arts1234")
    built.text_input(key="el_title").set_value("Film Studies")
    built.text_input(key="el_prereq").set_value("COMP1117")
    built.selectbox(key="el_target").set_value(1)
    built = click(built, "Add elective")
    assert "ARTS1234" in [c for sem in plan(built) for c in sem]
    assert "Elective" in [r for t in built.table for r in t.value["Type"]]
    assert "Every required course is scheduled once" in text(built)
    assert [b.label for b in built.button if b.label == "Remove elective"]


def test_elective_before_its_prerequisite_is_flagged(built):
    built.text_input(key="el_code").set_value("ARTS1234")
    built.text_input(key="el_prereq").set_value("COMP3314")
    built.selectbox(key="el_target").set_value(0)
    built = click(built, "Add elective")
    assert "ARTS1234 (semester 1) needs COMP3314" in text(built)


@pytest.mark.parametrize("bad_code", ["", "hello", "COMP1117"])
def test_invalid_or_duplicate_elective_is_rejected_in_plain_words(built, bad_code):
    before = plan(built)
    built.text_input(key="el_code").set_value(bad_code)
    built = click(built, "Add elective")
    assert plan(built) == before
    assert built.error and "Problem" in built.error[0].value


def test_removing_an_elective(built):
    built.text_input(key="el_code").set_value("ARTS1234")
    built = click(built, "Add elective")
    built.selectbox(key="el_remove").set_value("ARTS1234")
    built = click(built, "Remove elective")
    assert "ARTS1234" not in [c for sem in plan(built) for c in sem]


def test_pasted_text_with_a_cycle_is_reported_not_hidden(app):
    app.radio(key="source").set_value("Paste text").run()
    app.text_area(key="pasted").set_value(
        "COMP1001 Intro (6 credits)\n"
        "COMP2001 Alpha (6 credits) Prerequisite: COMP2002\n"
        "COMP2002 Beta (6 credits) Prerequisite: COMP2001\n"
    )
    at = click(app, "Build my plan")
    body = text(at)
    assert "Circular prerequisite" in body
    assert "COMP2001" in body and "COMP2002" in body
    assert "2 course(s) could not be scheduled" in body
    assert plan(at) == [["COMP1001"]]
    assert "Every required course is scheduled once" not in body


def test_completed_courses_are_left_out_of_the_plan(app):
    app.text_area(key="completed_text").set_value("COMP1117, MATH1013")
    at = click(app, "Build my plan")
    codes = [c for sem in plan(at) for c in sem]
    assert "COMP1117" not in codes and "MATH1013" not in codes
    assert "COMP2113" in codes


def test_empty_paste_and_missing_upload_give_plain_messages(app):
    app.radio(key="source").set_value("Paste text").run()
    at = click(app, "Build my plan")
    assert "Paste your requirement text" in at.error[0].value
    at.radio(key="source").set_value("Upload a file").run()
    at = click(at, "Build my plan")
    assert "Choose a PDF, text or CSV file" in at.error[0].value
    assert not at.table


def test_text_without_courses_gives_an_error(app):
    app.radio(key="source").set_value("Paste text").run()
    app.text_area(key="pasted").set_value("Welcome to the faculty.")
    at = click(app, "Build my plan")
    assert "No courses were found" in at.error[0].value
    assert not at.table


def test_reviews_are_loaded_into_the_score(app, monkeypatch):
    monkeypatch.setenv("COURSE_PLANNER_REVIEWS", str(REVIEWS_SAMPLE))
    at = click(app, "Build my plan")
    body = text(at)
    assert "review(s) covering" in body
    assert "of your courses from the local dataset" in body
    assert "no student reviews are loaded yet" not in body
    assert any(
        "Past student reviews" in row
        for table in at.table
        for row in table.value["Basis"]
    )


def test_saved_documents_can_be_deleted_from_the_app(built):
    assert "Saved documents: 1" in text(built)
    built = click(built, "Delete all saved documents")
    assert "Saved documents: 0" in text(built)
    assert "Deleted 1 saved document(s)" in text(built)


def test_reviews_behind_scores_are_shown_with_original_text(app, monkeypatch):
    monkeypatch.setenv("COURSE_PLANNER_REVIEWS", str(REVIEWS_SAMPLE))
    at = click(app, "Build my plan")
    assert not at.exception
    assert [e.label for e in at.expander] == ["Student reviews behind each score"]
    shown = [t.value for t in at.table if "Original text" in t.value.columns]
    assert shown and "Good intro course" in shown[0]["Original text"].iloc[0]


def test_no_review_panel_without_reviews(built):
    assert not built.expander
