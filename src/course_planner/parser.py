"""Extract courses and prerequisites from a requirement document.

Three input forms are supported, matching the proposal: plain text (also used
for pasted text), CSV, and PDF (turned into text with pdfplumber first).

Anything the parser cannot make sense of is reported in
``ParseResult.warnings`` rather than dropped silently.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from course_planner.models import Course, ParseResult
from course_planner.prerequisites import COURSE_CODE, parse_prerequisites

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".csv")

_CODE_RE = re.compile(COURSE_CODE)
_BULLET_RE = re.compile(r"^[\s\-*•·●▪◦\d.)]*?(?=[A-Za-z]{4}\s?\d{4})")
_HEADER_RE = re.compile(rf"^({COURSE_CODE})\b(.*)$")
_CONNECTOR_START_RE = re.compile(r"^\s*(?:(?:and|or)\b|[,;/&])", re.IGNORECASE)
_CONNECTOR_END_RE = re.compile(r"(?:\b(?:and|or)|[,;/&])\s*$", re.IGNORECASE)
_LABEL_RE = re.compile(
    r"\b(pre-?req(?:uisite)?s?|assess(?:ment)?s?|credits?)\s*[:=]", re.IGNORECASE
)
_CREDITS_RE = re.compile(r"(\d+)\s*(?:credits?|cr|units?)\b", re.IGNORECASE)
_TITLE_END_RE = re.compile(
    r"\(\s*\d+\s*(?:credits?|cr|units?)|\b\d+\s*(?:credits?|cr|units?)\b|[-–—:]\s*$",
    re.IGNORECASE,
)
_ITEM_SPLIT_RE = re.compile(r"\s*(?:[,;+]|\band\b)\s*", re.IGNORECASE)
_LEADING_COUNT_RE = re.compile(r"^(\d+)\b(?!\s*%)")
_TRAILING_JUNK = " \t-–—:|,;"


class UnsupportedFileError(ValueError):
    """Raised for file types other than PDF, plain text or CSV."""


class EmptyDocumentError(ValueError):
    """Raised when a document yields no readable text at all."""


def parse_document(data: bytes | str | Path, filename: str = "") -> ParseResult:
    """Parse an uploaded file. ``filename`` decides the format for ``bytes``."""
    if isinstance(data, Path):
        filename = filename or data.name
        data = data.read_bytes()
    suffix = Path(filename).suffix.lower()
    if isinstance(data, str):
        return parse_csv(data) if suffix == ".csv" else parse_text(data)
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(
            f"'{filename or 'This file'}' is not a supported file type. "
            "Please upload a PDF, plain text (.txt) or CSV file."
        )
    if suffix == ".pdf":
        return parse_text(extract_pdf_text(data))
    text = data.decode("utf-8-sig", errors="replace")
    return parse_csv(text) if suffix == ".csv" else parse_text(text)


def extract_pdf_text(data: bytes) -> str:
    """Return the text of every page of a PDF, one blank line between pages."""
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:  # pdfplumber/pdfminer raise many unrelated types
        raise EmptyDocumentError(
            "The PDF could not be read. It may be damaged or password-protected."
        ) from exc
    text = "\n\n".join(pages).strip()
    if not text:
        raise EmptyDocumentError(
            "No text was found in this PDF. It may be a scanned image; "
            "try pasting the text or uploading a CSV instead."
        )
    return text


def count_assessments(text: str) -> int | None:
    """Count graded assessments in a phrase like ``"3 assignments, midterm, final exam"``.

    Items starting with a number contribute that number; other items count as
    one. Percentage-only items (``"40% coursework"``) count as one item.
    Returns ``None`` when nothing countable is present.
    """
    total = 0
    for item in _ITEM_SPLIT_RE.split(text.strip().rstrip(".")):
        item = item.strip()
        if not item or item.lower() in {"none", "nil", "n/a", "-"}:
            continue
        match = _LEADING_COUNT_RE.match(item)
        total += int(match.group(1)) if match else 1
    return total or None


def parse_completed_courses(text: str) -> set[str]:
    """Course codes found in the student's optional list of completed courses."""
    return set(_codes(text))


def _codes(text: str) -> list[str]:
    # Tolerate "comp 1117" style spacing when students type codes by hand.
    normalised = re.sub(r"\b([A-Za-z]{4})\s?(\d{4}[A-Za-z]?)\b", r"\1\2", text).upper()
    return _CODE_RE.findall(normalised)


def parse_text(text: str) -> ParseResult:
    """Parse the text form of a requirement document."""
    if not text.strip():
        raise EmptyDocumentError("The document is empty, so there is nothing to parse.")

    blocks: list[list[str]] = []
    for raw_line in text.splitlines():
        line = _BULLET_RE.sub("", raw_line, count=1).strip()
        if not line:
            continue
        if _starts_course(line) and not _continues_previous(blocks):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)

    result = ParseResult()
    seen: set[str] = set()
    for block in blocks:
        course = _parse_block(block, result.warnings)
        if course.code in seen:
            result.warnings.append(
                f"{course.code} appears more than once; only the first entry was kept."
            )
            continue
        seen.add(course.code)
        result.courses.append(course)

    if not result.courses:
        result.warnings.append(
            "No course codes (like COMP1117) were found in this document."
        )
    return result


def _starts_course(line: str) -> bool:
    match = _HEADER_RE.match(line)
    if not match:
        return False
    return not _CONNECTOR_START_RE.match(match.group(2))


def _continues_previous(blocks: list[list[str]]) -> bool:
    """A code-led line right after a dangling "or"/"and"/"," is a wrapped prerequisite."""
    return bool(blocks) and bool(_CONNECTOR_END_RE.search(blocks[-1][-1]))


def _parse_block(block: list[str], warnings: list[str]) -> Course:
    header_match = _HEADER_RE.match(block[0])
    assert header_match  # guaranteed by _starts_course
    code = header_match.group(1)

    credits: int | None = None
    title_parts: list[str] = []
    values: dict[str, list[str]] = {"prereq": [], "assess": []}
    current: str | None = None

    segments = [seg for line in block for seg in line.split("|")]
    segments[0] = header_match.group(2)  # drop the leading code from the first segment
    for segment in segments:
        pieces = _LABEL_RE.split(segment)
        lead, labelled = pieces[0], zip(pieces[1::2], pieces[2::2], strict=True)
        if lead.strip():
            if current in values:
                values[current].append(lead.strip())
            else:
                title_parts.append(lead.strip())
                current = None
        for label, value in labelled:
            label = label.lower()
            if label.startswith("credit"):
                found = re.search(r"\d+", value)
                credits = credits or (int(found.group()) if found else None)
                current = None
            else:
                current = "prereq" if label.startswith("pre") else "assess"
                values[current].append(value.strip())

    head = " ".join(title_parts)
    found_credits = _CREDITS_RE.search(head)
    if found_credits and credits is None:
        credits = int(found_credits.group(1))
    title_end = _TITLE_END_RE.search(head)
    title = (head[: title_end.start()] if title_end else head).strip(_TRAILING_JUNK)

    prereq_text = " ".join(v for v in values["prereq"] if v)
    assess_text = " ".join(v for v in values["assess"] if v)
    if credits is None:
        warnings.append(f"{code}: credits were not found in the document.")
    return Course(
        code=code,
        title=title,
        credits=credits,
        prerequisites=parse_prerequisites(prereq_text),
        assessments=count_assessments(assess_text) if assess_text else None,
    )


_CSV_ALIASES = {
    "code": ("code", "course", "course code", "course_code"),
    "title": ("title", "name", "course title", "course name"),
    "credits": ("credits", "credit", "units", "cr"),
    "prerequisites": ("prerequisites", "prerequisite", "prereq", "prereqs"),
    "assessments": ("assessments", "assessment", "graded assessments"),
}


def parse_csv(text: str) -> ParseResult:
    """Parse a CSV with columns code, title, credits, prerequisites, assessments.

    Column names are case-insensitive and a few aliases are accepted. Only
    ``code`` is required.
    """
    if not text.strip():
        raise EmptyDocumentError("The CSV file is empty, so there is nothing to parse.")
    reader = csv.DictReader(io.StringIO(text))
    columns: dict[str, str] = {}
    for header in reader.fieldnames or []:
        for field, aliases in _CSV_ALIASES.items():
            if header.strip().lower() in aliases:
                columns.setdefault(field, header)
    if "code" not in columns:
        raise EmptyDocumentError(
            "The CSV needs a 'code' column (for example COMP1117) in its first row."
        )

    result = ParseResult()
    seen: set[str] = set()
    for line_no, row in enumerate(reader, start=2):
        def cell(field: str, row: dict[str, str] = row) -> str:
            return (row.get(columns[field]) or "").strip() if field in columns else ""

        codes = _codes(cell("code"))
        if not codes:
            if any((value or "").strip() for value in row.values()):
                result.warnings.append(f"Row {line_no}: no valid course code, row skipped.")
            continue
        code = codes[0]
        if code in seen:
            result.warnings.append(f"{code} appears more than once; only the first row was kept.")
            continue
        seen.add(code)

        credits = _int_or_none(cell("credits"))
        if credits is None:
            result.warnings.append(f"{code}: credits were not found in the document.")
        assessments = cell("assessments")
        result.courses.append(
            Course(
                code=code,
                title=cell("title"),
                credits=credits,
                prerequisites=parse_prerequisites(cell("prerequisites")),
                assessments=count_assessments(assessments),
            )
        )

    if not result.courses:
        result.warnings.append("No course rows were found in this CSV.")
    return result


def _int_or_none(value: str) -> int | None:
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None
