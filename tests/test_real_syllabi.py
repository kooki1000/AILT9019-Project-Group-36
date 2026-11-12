"""Optional checks on real programme syllabuses (not committed: they are the faculties' files).

Point ``COURSE_PLANNER_REAL_SYLLABI`` at a folder of PDFs to run them::

    COURSE_PLANNER_REAL_SYLLABI=~/syllabuses python -m pytest tests/test_real_syllabi.py

The checks are structural, not a labelled accuracy figure: they catch the failures seen on
the BEcon, BEng(CompSc) and BA syllabuses (paragraphs swallowed into titles, courses
without credits, duplicate or placeholder codes, no way to tell what is required).
"""

import os
from pathlib import Path

import pytest

from course_planner.parser import parse_document

FOLDER = os.environ.get("COURSE_PLANNER_REAL_SYLLABI")
PDFS = sorted(Path(FOLDER).expanduser().glob("*.pdf")) if FOLDER else []

pytestmark = pytest.mark.skipif(not PDFS, reason="COURSE_PLANNER_REAL_SYLLABI not set")


@pytest.mark.parametrize("pdf", PDFS, ids=lambda p: p.name)
def test_real_syllabus_is_read_sensibly(pdf):
    result = parse_document(pdf)
    courses = result.courses
    if not courses:  # a regulations document has no course list; it must say so
        assert any("regulations document" in w for w in result.warnings), "no courses found"
        return
    assert len({c.code for c in courses}) == len(courses)
    assert not any(c.code.startswith("XXXX") for c in courses)
    assert max(len(c.title) for c in courses) <= 120, "a paragraph was read as a title"
    # Some faculties omit credits for whole lists (e.g. BALLB's electives). That is fine as long
    # as it is never silent: every course without credits has a warning.
    warned = {w.split(":")[0] for w in result.warnings if "credits were not found" in w}
    assert {c.code for c in courses if c.credits is None} <= warned
    required = [c for c in courses if not c.elective]
    assert required, "every course was classed as an elective"
