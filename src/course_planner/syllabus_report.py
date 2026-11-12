"""Quick health report for trying the parser on any syllabus.

    python -m course_planner.syllabus_report path/to/syllabus.pdf [more files or folders]
    python -m course_planner.syllabus_report syllabus.pdf --all     # also list every course

For each document it prints how many courses were found, how many are required or
electives, what is missing, and a list of things that look wrong, so a new faculty's
format can be judged in seconds. It reads files locally and stores nothing.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from course_planner.models import ParseResult
from course_planner.parser import SUPPORTED_EXTENSIONS, EmptyDocumentError, parse_document

LONG_TITLE = 140  # some real course titles run past 100 characters
CATALOGUE_SIZE = 60
SHOWN = 8


@dataclass
class Report:
    name: str
    result: ParseResult | None = None
    error: str = ""
    suspicious: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def looks_ok(self) -> bool:
        return self.result is not None and bool(self.result.courses) and not self.suspicious


def inspect_document(path: Path, programme: str | None = None) -> Report:
    report = Report(path.name)
    try:
        report.result = parse_document(path, programme=programme)
    except (ValueError, EmptyDocumentError, OSError) as exc:
        report.error = str(exc)
        return report
    courses = report.result.courses
    if not courses:
        report.suspicious.append("no courses were found")
        return report
    no_credits = [c.code for c in courses if c.credits is None]
    if no_credits and len(no_credits) / len(courses) > 0.1:
        report.suspicious.append(
            f"{len(no_credits)} of {len(courses)} courses have no credits (more than 10%)"
        )
    long = [c.code for c in courses if len(c.title) > LONG_TITLE]
    if long:
        report.suspicious.append(
            f"{len(long)} title(s) over {LONG_TITLE} characters, a paragraph may have been "
            f"read as a title: {', '.join(long[:SHOWN])}"
        )
    empty = [c.code for c in courses if len(c.title) < 3]
    if empty:
        report.suspicious.append(
            f"{len(empty)} course(s) with no title: {', '.join(empty[:SHOWN])}"
        )
    if all(c.elective for c in courses):
        report.suspicious.append("every course was classed as an elective")
    if not any(c.prerequisites for c in courses):
        report.notes.append("no prerequisites found (normal if the document does not list any)")
    required = sum(not c.elective for c in courses)
    if required > CATALOGUE_SIZE:
        report.notes.append(
            f"{required} required courses is more than one programme; the app will ask for a "
            "course list instead of planning them all"
        )
    return report


def format_report(report: Report, show_all: bool = False) -> str:
    lines = [f"=== {report.name}"]
    if report.result is None:
        return "\n".join([*lines, f"  could not be read: {report.error}"])
    courses = report.result.courses
    required = sum(not c.elective for c in courses)
    lines.append(
        f"  courses: {len(courses)} "
        f"({required} required, {len(courses) - required} elective/choice)"
    )
    lines.append(
        f"  with credits: {sum(c.credits is not None for c in courses)}, "
        f"with prerequisites: {sum(bool(c.prerequisites) for c in courses)}, "
        f"with assessments: {sum(c.assessments is not None for c in courses)}"
    )
    if report.result.programmes:
        lines.append(
            f"  programmes in this file: {'; '.join(report.result.programmes)} "
            f"(read: {report.result.programme}; use --programme NAME for another)"
        )
    lines.append(f"  parser warnings: {len(report.result.warnings)}")
    lines.extend(f"    - {w}" for w in report.result.warnings[:SHOWN])
    if len(report.result.warnings) > SHOWN:
        lines.append(f"    ... and {len(report.result.warnings) - SHOWN} more")
    if report.suspicious:
        lines.append("  CHECK THESE:")
        lines.extend(f"    ! {s}" for s in report.suspicious)
    else:
        lines.append("  looks fine at a glance (still spot-check a few courses against the PDF)")
    lines.extend(f"  note: {n}" for n in report.notes)
    listing = courses if show_all else courses[:SHOWN]
    lines.append("  courses:" if show_all else f"  first {len(listing)} courses:")
    for c in listing:
        prereq = " and ".join(
            "(" + " or ".join(g) + ")" if len(g) > 1 else g[0] for g in c.prerequisites
        )
        lines.append(
            f"    {'E' if c.elective else 'R'} {c.code} | {c.title[:50]} | "
            f"{'?' if c.credits is None else c.credits} cr | prereq: {prereq or '-'}"
        )
    if not show_all and len(courses) > SHOWN:
        lines.append(f"    ... use --all to list all {len(courses)} (R = required, E = elective)")
    return "\n".join(lines)


def collect(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                sorted(p for p in path.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)
            )
        else:
            files.append(path)
    return files


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    show_all = "--all" in args
    programme = None
    if "--programme" in args:
        at = args.index("--programme")
        programme = args[at + 1] if at + 1 < len(args) else None
        del args[at : at + 2]
    paths = [Path(a).expanduser() for a in args if a != "--all"]
    if not paths:
        print(
            "usage: python -m course_planner.syllabus_report <file or folder> ... "
            "[--all] [--programme NAME]"
        )
        return 2
    reports = [inspect_document(p, programme) for p in collect(paths)]
    for report in reports:
        print(format_report(report, show_all))
    return 0 if reports and all(r.looks_ok or r.result is not None for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
