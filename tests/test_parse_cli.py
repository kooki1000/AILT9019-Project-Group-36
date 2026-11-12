import json
from pathlib import Path

from course_planner.parse_cli import main

SAMPLE = Path(__file__).parent.parent / "data" / "samples" / "sample_requirements.txt"


def test_prints_json_for_a_document(capsys):
    assert main([str(SAMPLE)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["courses"]) == 7 and data["warnings"] == []
    comp2119 = next(c for c in data["courses"] if c["code"] == "COMP2119")
    assert comp2119["prerequisites"] == [["COMP1117"], ["MATH1013", "MATH1853"]]


def test_errors_are_json_with_exit_code_1(capsys, tmp_path):
    bad = tmp_path / "plan.docx"
    bad.write_bytes(b"x")
    assert main([str(bad)]) == 1
    assert "not a supported file type" in json.loads(capsys.readouterr().out)["error"]
    assert main([str(tmp_path / "missing.txt")]) == 1
    empty = tmp_path / "e.txt"
    empty.write_text("Welcome.")
    assert main([str(empty)]) == 1


def test_usage_error(capsys):
    assert main([]) == 2
