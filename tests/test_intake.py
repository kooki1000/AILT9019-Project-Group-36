from course_planner.intake import read_document
from course_planner.models import Course, ParseResult
from course_planner.storage import DocumentStore

GOOD = b"COMP1117 Computer Programming (6 credits)\nCOMP2113 Programming Technologies (6 credits)\n"


def test_success_is_saved_for_later(tmp_path):
    store = DocumentStore(tmp_path / "db.sqlite3")
    result, notices = read_document(GOOD, "plan.txt", store)
    assert [c.code for c in result.courses] == ["COMP1117", "COMP2113"]
    assert notices == []
    assert store.load_parsed(GOOD) == result


def test_unsupported_type_is_rejected_without_fallback(tmp_path):
    store = DocumentStore(tmp_path / "db.sqlite3")
    store.save("plan.txt", b"data", ParseResult(courses=[Course("COMP1117")]))
    result, notices = read_document(b"data", "plan.docx", store)
    assert result is None
    assert notices[0][0] == "error" and "PDF, plain text" in notices[0][1]


def test_unreadable_pdf_without_cache_explains_what_to_try(tmp_path):
    store = DocumentStore(tmp_path / "db.sqlite3")
    result, notices = read_document(b"not a pdf", "plan.pdf", store)
    assert result is None
    level, message = notices[0]
    assert level == "error" and "could not be read" in message and "pasting the text" in message


def test_unreadable_pdf_falls_back_to_saved_result_for_same_bytes(tmp_path):
    store = DocumentStore(tmp_path / "db.sqlite3")
    saved = ParseResult(courses=[Course("COMP1117", "Programming", 6)])
    store.save("plan.pdf", b"not a pdf", saved)
    result, notices = read_document(b"not a pdf", "plan.pdf", store)
    assert result == saved
    assert notices[0][0] == "warning" and "saved result" in notices[0][1]


def test_document_without_courses_is_an_error(tmp_path):
    store = DocumentStore(tmp_path / "db.sqlite3")
    result, notices = read_document(b"Welcome to the faculty.", "intro.txt", store)
    assert result is None
    assert "No courses were found" in notices[0][1]
    assert store.list_documents() == []


def test_unwritable_store_only_warns(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    store = DocumentStore(blocker / "db.sqlite3")
    result, notices = read_document(GOOD, "plan.txt", store)
    assert result is not None
    assert notices == [("warning", "The result could not be saved on this computer.")]


def test_saved_result_for_another_degree_is_not_shown_as_the_requested_one(tmp_path):
    # Regression: a failed read fell back to the saved result even when it was for a
    # different degree of the same file than the one the student asked for.
    store = DocumentStore(tmp_path / "db.sqlite3")
    saved = ParseResult(
        [Course("ENGG1000", "Fundamentals", 6)],
        programmes=["COMPUTER ENGINEERING", "ELECTRICAL ENGINEERING"],
        programme="COMPUTER ENGINEERING",
    )
    store.save("plan.pdf", b"not a pdf", saved)

    other, notices = read_document(b"not a pdf", "plan.pdf", store, "ELECTRICAL ENGINEERING")
    assert other is None and notices[0][0] == "error"

    same, notices = read_document(b"not a pdf", "plan.pdf", store, "computer engineering")
    assert same is not None and notices[0][0] == "warning"

    default, _ = read_document(b"not a pdf", "plan.pdf", store)
    assert default is not None
