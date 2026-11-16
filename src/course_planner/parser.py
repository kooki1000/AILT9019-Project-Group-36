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
from dataclasses import dataclass, replace
from pathlib import Path

from course_planner.models import Course, ParseResult
from course_planner.prerequisites import (
    COURSE_CODE,
    is_none_text,
    parse_prerequisites,
    parse_prerequisites_detailed,
)

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

# Syllabus layouts (HKU faculty documents). Footnote markers such as ``*``, ``#`` or ``^``
# may follow a course code.
_MARK = r"[*#^†‡]*"
_DESC_RE = re.compile(rf"^({COURSE_CODE}){_MARK}\.\s+(\S.*)$")
_PAREN_CREDITS_RE = re.compile(r"\(\s*(\d+)\s*credits?\s*(?:\)|$)", re.IGNORECASE)
_EACH_CREDITS_RE = re.compile(
    r"\b(?:one|each|any|following)\b.*\(\s*(\d+)\s*credits?\s*\)\s*:?\s*$", re.IGNORECASE
)
_CHOOSE_ONE_RE = re.compile(r"\b(?:choose|select|take) (?:at least )?one of the following", re.I)
# Numbered regulation text ("4 Candidates ...", "(iv) ...", "LL 8. ...") and placeholder rows.
_NOT_HEADING_RE = re.compile(
    r"^(?:\(?\d+[\).]?\s|\([a-z]+\)\s|[A-Z]{1,3}\s?\d+\.\s|[A-Za-z]{2,4}[xX]{3,4})"
)
_SECTION_RE = re.compile(r"^SYLLABUS(?:ES)?$")  # a programme's own "<TITLE> / SYLLABUS" heading
_PROGRAMME_RE = re.compile(
    r"^(?:(?:MAJOR|MINOR) IN\b|Minor in\b|SYLLABUSES? FOR THE DEGREE OF\b)"
)
_YEARS = r"[1-6](?:\s*(?:or|,|/)\s*[1-6])*"
_ROW_RE = re.compile(rf"^({COURSE_CODE}){_MARK}\s+(.+?)\s+(\d{{1,2}})$")
_ROW_YEAR_RE = re.compile(rf"^({COURSE_CODE}){_MARK}\s+(.+?)\s+{_YEARS}\s+(\d{{1,2}})$")
_SLASH_ROW_RE = re.compile(rf"^({COURSE_CODE}){_MARK}\s*/\s*(.+?)\s*/\s*(\d{{1,2}})$")
_OR_ROW_RE = re.compile(rf"^({COURSE_CODE}){_MARK}\s+or\s+(?!{COURSE_CODE})(.+?)(?:\s+or)?$")
_BARE_ROW_RE = re.compile(rf"^({COURSE_CODE}){_MARK}\s+(\S.*)$")
_YEAR_CREDITS_RE = re.compile(rf"^{_YEARS}\s+(\d{{1,2}})$")
_TABLE_HEADER_RE = re.compile(r"^course\s*code\b", re.IGNORECASE)
_FIELD_RE = re.compile(
    r"^(pre-?requisites?|assessments?|mutually exclusive with|co-?requisites?)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_INLINE_FIELD_RE = re.compile(r"\b(pre-?requisites?|assessments?)\s*:\s*(.*)$", re.IGNORECASE)
_ELECTIVE_HEAD_RE = re.compile(
    r"elective|to be chosen|chosen from|choose (?:any|\d+|from|at least one)|"
    r"select (?:any|\d+|from)|take (?:one|any|\d+)|in lieu|must either|either complete",
    re.IGNORECASE,
)
_REQUIRED_HEAD_RE = re.compile(
    r"\b(core|required|compulsory|capstone|foundation|introductory|advanced|complete all|"
    r"major|prerequisite)\b",
    re.IGNORECASE,
)
_NOISE_RE = re.compile(r"^(?:\d{1,3}|[_\-=]{5,})$")
_STUCK_DIGIT_RE = re.compile(r"(?<=[a-z])\d$")
_CONDITION_RE = re.compile(r"consent|permission|approval|standing|at least", re.IGNORECASE)
MAX_TITLE_LINES = 2
MAX_HEADING_LENGTH = 90  # wrapped sentences of regulations are longer than headings
# "CODE. Title 3": a bare number is taken as credits only if it is a usual credit value.
BARE_CREDIT_VALUES = (0, 3, 6, 9, 12)
MAX_WRAPPED_CREDITS = 6  # a heading's "(12 credits)" total is not a wrapped title's credits


class UnsupportedFileError(ValueError):
    """Raised for file types other than PDF, plain text or CSV."""


class EmptyDocumentError(ValueError):
    """Raised when a document yields no readable text at all."""


def parse_document(
    data: bytes | str | Path, filename: str = "", programme: str | None = None
) -> ParseResult:
    """Parse an uploaded file. ``filename`` decides the format for ``bytes``.

    ``programme`` picks one degree when the document contains several (see
    ``ParseResult.programmes``); the first is read by default.
    """
    if isinstance(data, Path):
        filename = filename or data.name
        data = data.read_bytes()
    suffix = Path(filename).suffix.lower()
    if isinstance(data, str):
        return parse_csv(data) if suffix == ".csv" else parse_text(data, programme)
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(
            f"'{filename or 'This file'}' is not a supported file type. "
            "Please upload a PDF, plain text (.txt) or CSV file."
        )
    text = document_text(data, filename)
    return parse_csv(text) if suffix == ".csv" else parse_text(text, programme)


def document_text(data: bytes, filename: str) -> str:
    """Plain text of an uploaded document (PDFs are extracted first).

    Used by the optional AI parse. The file type is not checked here; callers
    use it only for documents ``parse_document`` already accepted.
    """
    if Path(filename).suffix.lower() == ".pdf":
        return extract_pdf_text(data)
    return data.decode("utf-8-sig", errors="replace")


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


def parse_text(text: str, programme: str | None = None) -> ParseResult:
    """Parse the text form of a requirement document or faculty syllabus."""
    if not text.strip():
        raise EmptyDocumentError("The document is empty, so there is nothing to parse.")
    reader = _Reader(programme)
    for raw_line in text.splitlines():
        line = _BULLET_RE.sub("", raw_line, count=1).strip()
        if line and not _NOISE_RE.match(line):
            reader.feed(line)
    return reader.finish()


@dataclass
class _Entry:
    """One course as found in the text, before duplicates are merged."""

    # "legacy" (labelled block), "row" (table row), "ref" (a bare "CODE title" mention in a
    # list) or "desc" (course description)
    kind: str
    course: Course
    prereq_text: str = ""
    # One vote per table row / block that lists the course: True when that listing is elective.
    votes: tuple[bool, ...] = ()
    programme: int | None = None  # which programme section listed it; None: shared catalogue
    # Credits that came from a wrapped line, not the header line: weaker evidence.
    weak_credits: bool = False


@dataclass
class _Description:
    """A course description being read: its title may wrap and its fields follow."""

    code: str
    title_parts: list[str]
    credits: int | None
    title_lines_left: int
    values: dict[str, list[str]]
    field: str | None = None
    weak_credits: bool = False
    seen_field: bool = False  # Prerequisite:/Assessment: followed: a description, not a list item
    body: list[str] | None = None  # prose lines after the header (checked for headings later)
    choice: bool = False  # the entry above ended in "or": this is one of several alternatives
    ends_or: bool = False  # this entry itself ends in "or" / "; OR"
    plain: bool = False  # header written without a period: "CODE Title (6 credits)"
    catalogue: bool = False  # after a closed programme section: never a requirement list


class _Reader:
    """Reads a document line by line.

    Three layouts are recognised, and may be mixed in one document:

    * labelled blocks (``COMP1117 Programming (6 credits)`` then ``Prerequisite:`` ...),
    * table rows (``COMP1117 Computer programming 6``, optionally with a year column),
    * course descriptions (``COMP1117. Computer programming (6 credits)`` followed by prose
      and ``Prerequisite:`` / ``Assessment:`` lines).

    Prose is never added to a title or a field; only a wrapped list ("... and" / "(A or")
    continues the line above.
    """

    def __init__(self, programme: str | None = None) -> None:
        self.wanted = programme
        self.section = 0
        self.names: list[str] = []
        self.prev_line = ""
        self.entries: list[_Entry] = []
        self.warnings: list[str] = []
        self.legacy: list[str] | None = None
        self.desc: _Description | None = None
        self.table_mode = False
        self.year_column = False
        self.elective = False
        self.heading: tuple[int, bool | None] = (-99, None)
        self.line_no = 0
        self.open_cluster: list[int] = []  # row entries still waiting for their credits
        self.carry: int | None = None  # credits for the next bare "CODE title" row
        self.alt_open = False
        self.rows_closed = False  # a later major/minor section: its tables are not ours
        self.after_or = False  # the previous list entry ended in "or"
        self.default_credits: int | None = None  # "one of the following ... (6 credits):"
        # "choose one of the following": covers the list entries below it, but not table rows
        # (a table's choose-one group is already marked by its "A or B" layout).
        self.choose = False
        self.regulations = False  # the document opens as "REGULATIONS FOR ..."

    # ------------------------------------------------------------------ input

    def feed(self, line: str) -> None:
        previous, self.prev_line = self.prev_line, line
        self.line_no += 1
        if _SECTION_RE.match(line) and self._starts_programme(previous):
            return
        if self.line_no <= 3 and line.upper().startswith("REGULATIONS FOR"):
            self.regulations = True
        desc = self.desc
        if desc is not None and desc.field in ("prereq", "assess") and _is_unfinished(
            desc.values[desc.field]
        ):
            desc.values[desc.field].append(line)  # a wrapped list, even if it starts with a code
            return
        if _HEADER_RE.match(line):
            if self.legacy is not None and _CONNECTOR_END_RE.search(self.legacy[-1]):
                self.legacy.append(line)  # a wrapped prerequisite list
                return
            if self._code_line(line):
                return
        self._other_line(line)

    def _code_line(self, line: str) -> bool:
        desc = _DESC_RE.match(line)
        if desc:
            self._start_description(desc.group(1), desc.group(2))
            return True
        if self.desc is not None and not self.desc.plain:
            return False  # inside a description, a code-led line is prose
        if self.rows_closed:
            # Another programme's tables are skipped, but course descriptions that follow
            # them still carry the prerequisites and assessments: read them as catalogue.
            header = _HEADER_RE.match(line)
            if header and _PAREN_CREDITS_RE.search(line) and "|" not in line:
                code = header.group(1)
                rest = re.sub(rf"^{_MARK}", "", line[len(code):]).strip()
                if _plausible_title(rest):
                    self._start_description(code, rest, plain=True)
                    return True
            return header is not None
        plain = "|" not in line and ":" not in line
        if plain:
            slash = _SLASH_ROW_RE.match(line)
            if slash:
                credits = int(slash.group(3))
                self._add_row(slash.group(1), slash.group(2), credits, cluster=True)
                self.carry, self.alt_open = credits, True
                return True
            row = (self.year_column and _ROW_YEAR_RE.match(line)) or _ROW_RE.match(line)
            if row and _plausible_title(row.group(2)):
                self._add_row(row.group(1), row.group(2), int(row.group(3)))
                return True
            if self.table_mode:
                either = _OR_ROW_RE.match(line)
                if either and _plausible_title(either.group(2)):
                    self._add_row(either.group(1), either.group(2), None, cluster=True)
                    self.alt_open = True
                    return True
                bare = _BARE_ROW_RE.match(line)
                if bare and self.alt_open and _plausible_title(bare.group(2)):
                    self._add_row(bare.group(1), bare.group(2), self.carry, cluster=True)
                    self.carry, self.alt_open = None, False
                    return True
                if bare and _plausible_title(bare.group(2)) and _CONNECTOR_START_RE.match(
                    bare.group(2)
                ) is None:
                    self._add_reference(bare.group(1), bare.group(2).split(" / ")[0])
                    return True
        if self.table_mode and not self._looks_labelled(line):
            return False  # prose that merely starts with a course code
        header = _HEADER_RE.match(line)
        if (
            header
            and "|" not in line
            and (self.desc is None or self.desc.plain)
            and not _LABEL_RE.search(line)
            and _starts_course(line)
        ):
            code = header.group(1)
            rest = re.sub(rf"^{_MARK}", "", line[len(code):]).strip()
            if _plausible_title(rest):
                self._start_description(code, rest, plain=True)
                return True
        if _starts_course(line):
            self._close()
            self.legacy = [line]
            return True
        return False

    @staticmethod
    def _looks_labelled(line: str) -> bool:
        """A labelled-block header carries a field separator, a label or a credits note."""
        return "|" in line or bool(_LABEL_RE.search(line) or _PAREN_CREDITS_RE.search(line))

    def _other_line(self, line: str) -> None:
        if self.table_mode and _PROGRAMME_RE.match(line) and any(
            e.kind == "row" for e in self.entries
        ):
            self._close()
            self.rows_closed = True
            return
        if _TABLE_HEADER_RE.match(line):
            self._close()
            if self.rows_closed:
                return
            self.table_mode = True
            self.year_column = "year" in line.lower()
            at, flag = self.heading
            self.elective = bool(flag) and self.line_no - at <= 2
            self.open_cluster, self.carry, self.alt_open = [], None, False
            self.after_or = False
            return
        numbers = _YEAR_CREDITS_RE.match(line) if self.table_mode else None
        if numbers:
            credits = int(numbers.group(1))
            for index in self.open_cluster:
                entry = self.entries[index]
                entry.course = replace(entry.course, credits=credits)
            if self.open_cluster:
                self.carry, self.alt_open = credits, True
            self.open_cluster = []
            return
        desc = self.desc
        if desc is not None and self._description_line(line):
            return
        if self.legacy is not None:
            self.legacy.append(line)
            return
        self._apply_heading(line)

    def _starts_programme(self, title: str) -> bool:
        """A standalone "SYLLABUS" line opens a programme; ``title`` is the line above it."""
        if (
            not title
            or len(title) > 90
            or title.endswith(".")
            or title[-1:].isdigit()
            or _CODE_RE.search(title)  # a table row above a repeated page header
            or title.strip() in self.names  # the same title again: a running header
        ):
            return False
        self._close()
        if self.names:  # a further programme: start from a clean slate
            self.section = len(self.names)
            self.rows_closed = self.table_mode = self.elective = self.choose = False
            self.open_cluster, self.carry, self.alt_open = [], None, False
            self.default_credits, self.after_or, self.heading = None, False, (-99, None)
        self.names.append(title.strip())
        return True

    def _apply_heading(self, line: str) -> None:
        if _CHOOSE_ONE_RE.search(line) and len(line) <= 170 and not line.endswith("."):
            self.choose = True  # even when the heading also says "Capstone course"
            each = _EACH_CREDITS_RE.search(line)
            self.default_credits = int(each.group(1)) if each else None
            return
        flag = _heading_flag(line)
        if flag is None:
            if _is_plain_heading(line):
                self.default_credits = None  # a new section: the per-course credits ended
            return
        self.choose = False
        self.heading, self.elective = (self.line_no, flag), flag
        each = _EACH_CREDITS_RE.search(line)
        self.default_credits = int(each.group(1)) if each else None

    # ------------------------------------------------------------ descriptions

    def _start_description(self, code: str, rest: str, plain: bool = False) -> None:
        self._close()
        raw_rest = rest
        credits: int | None = None
        found = _PAREN_CREDITS_RE.search(rest)
        if found:
            credits, rest = int(found.group(1)), rest[: found.start()]  # drop any note after it
        alternative = any(
            re.search(r"(?:\bor|;)\s*$", text, re.IGNORECASE) for text in (raw_rest, rest)
        )
        weak = False
        if credits is None and self.default_credits is not None:
            credits, weak = self.default_credits, True
        trailing = None if found else re.search(r"\s+(\d{1,2})\s*$", rest)
        if trailing and int(trailing.group(1)) in BARE_CREDIT_VALUES:
            credits, weak, found = int(trailing.group(1)), True, True
            rest = rest[: trailing.start()]
        self.desc = _Description(
            code, [rest.strip()], credits, 0 if found else MAX_TITLE_LINES,
            {"prereq": [], "assess": []}, choice=self.after_or, ends_or=alternative,
            weak_credits=weak, plain=plain, catalogue=self.rows_closed,
        )

    def _description_line(self, line: str) -> bool:
        desc = self.desc
        assert desc is not None
        field = _FIELD_RE.match(line)
        if field is None and desc.field is None:
            field = _INLINE_FIELD_RE.search(line)  # "... in Hong Kong. Assessment: 60% ..."
        if field:
            desc.seen_field = True
            name = field.group(1).lower()
            desc.field = "prereq" if name.startswith("pre") else (
                "assess" if name.startswith("assess") else "ignore"
            )
            if desc.field != "ignore":
                desc.values[desc.field].append(field.group(2).strip())
            return True
        if (
            desc.field is None
            and desc.title_lines_left > 0
            and len(line) <= 90
            and ". " not in line
            and not line.endswith(".")
        ):
            # Join first: the "(6 credits)" note itself can wrap ("... (6" / "credits)").
            joined = " ".join([*desc.title_parts, line])
            found = _PAREN_CREDITS_RE.search(joined)
            wrapped = bool(re.search(r"\(\s*\d*\s*$", desc.title_parts[-1]))
            if found and not wrapped and (
                _heading_flag(line) is not None
                or int(found.group(1)) > MAX_WRAPPED_CREDITS
                or not re.search(r"[a-z]", line)  # ALL CAPS, e.g. "SECOND YEAR (63 credits)"
            ):
                found = None  # a heading, not this title's wrapped credits note
            if found:
                desc.title_parts = [joined[: found.start()].strip()]
                desc.credits = int(found.group(1))
                desc.weak_credits = not wrapped
                desc.title_lines_left = 0
            elif _may_continue(desc.title_parts[-1]):
                desc.title_parts.append(line)
                desc.title_lines_left -= 1
            else:
                desc.title_lines_left = 0  # the title was complete; this is the description
                desc.body = [*(desc.body or []), line]
            return True
        if desc.field in ("prereq", "assess") and (
            _is_unfinished(desc.values[desc.field]) or _CONNECTOR_START_RE.match(line)
        ):
            desc.values[desc.field].append(line)
            return True
        if desc.body is None:
            desc.body = []
        desc.body.append(line)
        return True  # prose between the header and the fields

    # ---------------------------------------------------------------- output

    def _add_row(self, code: str, title: str, credits: int | None, cluster: bool = False) -> None:
        self._close()
        elective = self.elective or cluster
        course = Course(code, _clean_title(title), credits, elective=elective)
        self.entries.append(_Entry("row", course, votes=(elective,), programme=self.section))
        if credits is None:
            self.open_cluster.append(len(self.entries) - 1)
        else:
            self.open_cluster = []

    def _add_reference(self, code: str, title: str) -> None:
        """A course merely mentioned in a list (no credits): never a requirement by itself."""
        self._close()
        self.entries.append(
            _Entry("ref", Course(code, _clean_title(title)), programme=self.section)
        )

    def _close(self) -> None:
        if self.legacy is not None:
            course, prereq_text = _parse_block(self.legacy)
            course = replace(course, elective=self.elective)
            self.legacy = None
            # A fragment with no real title and no fields is prose that began with a code.
            titled = len(re.findall(r"[A-Za-z]", course.title)) >= 3 and course.title[:1].isalnum()
            if titled or prereq_text or course.assessments:
                self.entries.append(_Entry("legacy", course, prereq_text, (course.elective,)))
        if self.desc is not None:
            desc, self.desc = self.desc, None
            prereq_text = " ".join(v for v in desc.values["prereq"] if v)
            assess_text = " ".join(v for v in desc.values["assess"] if v)
            course = Course(
                desc.code,
                _clean_title(" ".join(p for p in desc.title_parts if p)),
                desc.credits,
                parse_prerequisites(prereq_text),
                count_assessments(assess_text) if assess_text else None,
            )
            body = desc.body or []
            tail = [desc.title_parts[-1], *body[:1]]
            wrapped_or = any(re.search(r"\bor\s*$", t, re.IGNORECASE) for t in tail)
            listed = not desc.seen_field and not desc.catalogue
            ends_or = listed and (desc.ends_or or wrapped_or)
            self.after_or = ends_or
            choice = desc.choice or ends_or
            votes = (self.elective or self.choose or choice,) if listed else ()
            if listed:
                # A list item. Headings written between list items are read as body text of
                # the item above; they classify the entries that follow.
                for line in desc.body or []:
                    self._apply_heading(line)
            self.entries.append(
                _Entry(
                    "desc", course, prereq_text, votes, weak_credits=desc.weak_credits,
                    programme=self.section if votes else None,
                )
            )

    def finish(self) -> ParseResult:
        self._close()
        result = ParseResult(warnings=self.warnings)
        entries = self.entries
        if len(self.names) > 1:
            chosen = self._chosen_programme(result)
            result.programmes, result.programme = list(self.names), self.names[chosen]
            entries = [e for e in entries if e.programme in (None, chosen)]
        merged: dict[str, _Entry] = {}
        for entry in entries:
            code = entry.course.code
            if code not in merged:
                merged[code] = entry
            elif entry.kind == merged[code].kind == "legacy":
                result.warnings.append(
                    f"{code} appears more than once; only the first entry was kept."
                )
            else:
                merged[code] = _merge(merged[code], entry)
        has_tables = any(e.votes for e in entries if e.kind != "legacy")
        in_document = set(merged)
        for entry in merged.values():
            # Elective only if every list that names the course says so. A course that is only
            # described (or mentioned) in a document with requirement tables is not required.
            elective = all(entry.votes) if entry.votes else has_tables
            course = replace(
                entry.course,
                elective=elective,
                prerequisites=_without_itself(entry.course, _soft_groups(entry, in_document)),
            )
            result.courses.append(course)
            if course.credits is None:
                result.warnings.append(f"{course.code}: credits were not found in the document.")
            warning = _unchecked_prerequisite_warning(
                course.code, entry.prereq_text, course.prerequisites
            )
            if warning:
                result.warnings.append(warning)
        if not result.courses:
            result.warnings.append("No course codes (like COMP1117) were found in this document.")
            if self.regulations:
                result.warnings.append(
                    "This looks like a regulations document, which does not list courses. "
                    "Upload the matching syllabus ('Syllabuses for the degree of ...')."
                )
        return result

    def _chosen_programme(self, result: ParseResult) -> int:
        if self.wanted:
            wanted = self.wanted.strip().lower()
            for index, name in enumerate(self.names):
                if name.lower() == wanted:
                    return index
            result.warnings.append(
                f"Programme '{self.wanted}' was not found in this document; "
                f"showing '{self.names[0]}'."
            )
        return 0


def _unchecked_prerequisite_warning(
    code: str, text: str, groups: tuple[tuple[str, ...], ...]
) -> str | None:
    """Say so when a prerequisite's wording cannot be fully checked (no codes, or a condition)."""
    text = text.strip()
    if not text or is_none_text(text):
        return None
    if groups and not _CONDITION_RE.search(text):
        return None
    shown = text if len(text) <= 80 else text[:77] + "..."
    return f'{code}: the prerequisite "{shown}" is not (only) course codes, so it was not checked.'


def _soft_groups(entry: _Entry, in_document: set[str]) -> tuple[tuple[str, ...], ...]:
    """Groups with a no-course alternative ("or comparable level"), kept when usable for ordering.

    They are kept only if one of their courses is in the document; otherwise they could never be
    satisfied and would wrongly stop the course from being planned.
    """
    if not entry.prereq_text:
        return ()
    soft = parse_prerequisites_detailed(entry.prereq_text)[1]
    return tuple(group for group in soft if any(code in in_document for code in group))


def _without_itself(
    course: Course, extra: tuple[tuple[str, ...], ...] = ()
) -> tuple[tuple[str, ...], ...]:
    """A course is never its own prerequisite (text such as "or take X and Y together")."""
    groups = (
        tuple(c for c in group if c != course.code)
        for group in (*course.prerequisites, *extra)
    )
    unique: list[tuple[str, ...]] = []
    for group in groups:
        if group and group not in unique:
            unique.append(group)
    return tuple(unique)


def _merge(first: _Entry, second: _Entry) -> _Entry:
    """Combine two entries for one course (table row, mention, description, or repeats).

    Descriptions are the most informative, so on every field the first non-empty value
    from a description wins; otherwise the earlier entry does. Credits written on a
    header line beat credits taken from a wrapped line.
    """
    ranked = sorted((first, second), key=lambda e: e.kind != "desc")
    a, b = ranked
    credited = sorted(
        (e for e in ranked if e.course.credits is not None), key=lambda e: e.weak_credits
    )
    with_prereqs = next((e for e in ranked if e.course.prerequisites), a)
    course = Course(
        code=a.course.code,
        title=a.course.title or b.course.title,
        credits=credited[0].course.credits if credited else None,
        prerequisites=with_prereqs.course.prerequisites,
        assessments=next(
            (e.course.assessments for e in ranked if e.course.assessments is not None), None
        ),
    )
    prereq_text = with_prereqs.prereq_text or a.prereq_text or b.prereq_text
    kind = first.kind if first.kind != "ref" else second.kind
    weak = credited[0].weak_credits if credited else False
    return _Entry(kind, course, prereq_text, first.votes + second.votes, weak)


def _may_continue(title: str) -> bool:
    """A title wraps only after a comma, colon, hyphen, connector or open bracket."""
    return bool(re.search(r"[,:;(\-–—]\s*$", title) or _is_unfinished([title]))


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+(?:or|and)$", "", title.strip())
    title = re.split(r"\s*[*#^†‡]", title.strip())[0]  # a footnote marker ends the title
    title = title.strip(" \t–—-:")
    return _STUCK_DIGIT_RE.sub("", title).strip()


def _plausible_title(title: str) -> bool:
    """Reject prose that merely begins with a course code (e.g. "ECON1210 and a statistics...")."""
    return (
        not re.match(r"(and|or)\b", title)
        and ". " not in title
        and len(title) <= 120
        and not _CODE_RE.search(title)  # a second course code means a sentence, not a title
    )


def _is_plain_heading(line: str) -> bool:
    """A short, capitalised line without sentence punctuation, whatever it is about."""
    limit = 170 if line.endswith(":") else MAX_HEADING_LENGTH
    return (
        len(line) <= limit
        and not line.endswith(".")
        and not _NOT_HEADING_RE.match(line)
        and not line[:1].islower()
        and not line.startswith("(")
    )


def _heading_flag(line: str) -> bool | None:
    """True for an elective-list heading, False for a required one, None for other text."""
    if len(line) > (170 if line.endswith(":") else MAX_HEADING_LENGTH) or line.endswith("."):
        return None
    if _NOT_HEADING_RE.match(line) or line[:1].islower():
        return None  # regulation text, a wrapped sentence, or a "CODExxxx" placeholder row
    if _ELECTIVE_HEAD_RE.search(line):
        return True
    return False if _REQUIRED_HEAD_RE.search(line) else None


def _is_unfinished(parts: list[str]) -> bool:
    """True when the text collected so far stops at a connector or inside brackets."""
    text = " ".join(parts).rstrip()
    return bool(_CONNECTOR_END_RE.search(text)) or text.count("(") > text.count(")")


def _starts_course(line: str) -> bool:
    match = _HEADER_RE.match(line)
    if not match:
        return False
    return not _CONNECTOR_START_RE.match(match.group(2))


def _continues_previous(blocks: list[list[str]]) -> bool:
    """A code-led line right after a dangling "or"/"and"/"," is a wrapped prerequisite."""
    return bool(blocks) and bool(_CONNECTOR_END_RE.search(blocks[-1][-1]))


def _parse_block(block: list[str]) -> tuple[Course, str]:
    header_match = _HEADER_RE.match(block[0])
    assert header_match  # guaranteed by _starts_course
    code = header_match.group(1)

    credits: int | None = None
    title_parts: list[str] = []
    values: dict[str, list[str]] = {"prereq": [], "assess": []}
    current: str | None = None

    # Each "|"-separated field is a segment; ``new_line`` marks the first field of a
    # physical line. The first line loses its leading code.
    lines = [header_match.group(2), *block[1:]]
    segments = [
        (seg, position == 0) for line in lines for position, seg in enumerate(line.split("|"))
    ]
    for segment, new_line in segments:
        pieces = _LABEL_RE.split(segment)
        lead, labelled = pieces[0], zip(pieces[1::2], pieces[2::2], strict=True)
        if lead.strip():
            title_done = bool(_TITLE_END_RE.search(" ".join(title_parts)))
            if current is None and new_line and title_done:
                continue  # prose or a heading after a complete header line
            if current in values:
                # A fresh line after a labelled value only continues it when the value
                # was cut off mid-list ("... and" / "(A or"). Otherwise it is a section
                # heading or stray prose, and must not be counted as part of the value.
                if not new_line or _is_unfinished(values[current]):
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
    course = Course(
        code=code,
        title=title,
        credits=credits,
        prerequisites=parse_prerequisites(prereq_text),
        assessments=count_assessments(assess_text) if assess_text else None,
    )
    return course, prereq_text


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
            if _header_key(header) in {_header_key(alias) for alias in aliases}:
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
        prerequisites = parse_prerequisites(cell("prerequisites"))
        warning = _unchecked_prerequisite_warning(code, cell("prerequisites"), prerequisites)
        if warning:
            result.warnings.append(warning)
        result.courses.append(
            Course(
                code=code,
                title=cell("title"),
                credits=credits,
                prerequisites=prerequisites,
                assessments=count_assessments(assessments),
            )
        )

    if not result.courses:
        result.warnings.append("No course rows were found in this CSV.")
    return result


def _header_key(header: str) -> str:
    """Compare column names ignoring case, spaces, hyphens and "(s)".

    "Pre-requisite(s)" and "prerequisites" give the same key.
    """
    return re.sub(r"[^a-z]", "", header.lower().replace("(s)", "s"))


def _int_or_none(value: str) -> int | None:
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None
