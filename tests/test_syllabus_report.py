from pathlib import Path

from course_planner.syllabus_report import collect, format_report, inspect_document, main

SYLLABI = Path(__file__).parent / "fixtures" / "syllabi"


def test_good_document_looks_fine():
    report = inspect_document(SYLLABI / "tables_and_descriptions.txt")
    text = format_report(report)
    assert "courses: 10" in text and "required" in text
    assert report.suspicious == []


def test_report_lists_every_course_with_all(capsys):
    assert main([str(SYLLABI / "catalogue_descriptions.txt"), "--all"]) == 0
    out = capsys.readouterr().out
    assert "HIST2001" in out and "(HIST1002 or HIST1003)" in out and "R HIST3001" in out


def test_problems_are_called_out(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("ARTS1001 Course one\nARTS1002 Course two\n")
    text = format_report(inspect_document(bad))
    assert "CHECK THESE" in text and "no credits" in text


def test_unreadable_and_empty_files_are_reported(tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("Welcome to the faculty.")
    assert "no courses were found" in format_report(inspect_document(notes))
    docx = tmp_path / "plan.docx"
    docx.write_bytes(b"x")
    assert "could not be read" in format_report(inspect_document(docx))
    assert main([str(docx)]) == 1
    assert main([]) == 2


def test_folders_are_expanded_to_supported_files():
    names = {p.name for p in collect([SYLLABI])}
    assert names == {
        "catalogue_descriptions.txt", "law_style.txt", "list_style.txt", "multi_programme.txt",
        "table_year_column.txt", "tables_and_descriptions.txt",
    }


def test_catalogue_sized_documents_get_a_note_not_a_problem(tmp_path):
    big = tmp_path / "catalogue.txt"
    big.write_text("\n".join(f"ARTS{n:04d}. Course {n} (6 credits)" for n in range(1000, 1070)))
    report = inspect_document(big)
    assert report.suspicious == []
    assert any("course list" in note for note in report.notes)


def test_report_names_the_programmes_and_accepts_a_choice(capsys):
    path = str(SYLLABI / "multi_programme.txt")
    assert main([path, "--programme", "ELECTRICAL ENGINEERING"]) == 0
    out = capsys.readouterr().out
    assert "COMPUTER ENGINEERING; ELECTRICAL ENGINEERING" in out
    assert "read: ELECTRICAL ENGINEERING" in out
