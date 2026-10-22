from course_planner.models import Course, ParseResult
from course_planner.storage import DocumentStore, result_from_json, result_to_json

RESULT = ParseResult(
    courses=[
        Course("COMP1117", "Programming", 6, (), 5),
        Course("COMP2119", "Data Structures", 6, (("COMP1117",), ("MATH1013", "MATH1853")), None),
    ],
    warnings=["COMP2119: something"],
)


def test_json_round_trip():
    assert result_from_json(result_to_json(RESULT)) == RESULT


def test_save_then_load_by_content(tmp_path):
    store = DocumentStore(tmp_path / "db.sqlite3")
    store.save("plan.txt", b"hello", RESULT)
    assert store.load_parsed(b"hello") == RESULT
    assert store.load_parsed(b"other") is None
    assert [d.filename for d in store.list_documents()] == ["plan.txt"]


def test_saving_same_content_twice_keeps_one_row(tmp_path):
    store = DocumentStore(tmp_path / "db.sqlite3")
    store.save("a.txt", b"x", RESULT)
    store.save("b.txt", b"x", RESULT)
    assert [d.filename for d in store.list_documents()] == ["b.txt"]


def test_delete_all_removes_everything(tmp_path):
    store = DocumentStore(tmp_path / "db.sqlite3")
    store.save("a.txt", b"x", RESULT)
    store.save("b.txt", b"y", RESULT)
    assert store.delete_all() == 2
    assert store.list_documents() == []
    assert store.load_parsed(b"x") is None


def test_empty_store_does_not_create_a_file(tmp_path):
    store = DocumentStore(tmp_path / "nested" / "db.sqlite3")
    assert store.load_parsed(b"x") is None
    assert store.list_documents() == []
    assert store.delete_all() == 0
    assert not (tmp_path / "nested").exists()
