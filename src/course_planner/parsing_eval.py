"""Parsing acceptance check from the proposal's must-have #1.

The proposal calls parsing done only when at least 95% of courses and
prerequisite links are pulled out correctly from the test documents. This
module measures that against hand-made labels, one JSON file per document::

    {"COMP2119": {"credits": 6, "assessments": 5,
                  "prerequisites": [["COMP1117"], ["MATH1013", "MATH1853"]]}}

A *link* is one prerequisite group of one course, so ``COMP1117 and (MATH1013
or MATH1853)`` is two links and getting an "or" group half right earns neither.
Both recall (how much of the truth was found) and precision (how much of what
was found is true) must reach the threshold. Credits and assessment counts are
reported too, but they are not part of the proposal's bar.

Run on a folder of labels and one or more folders of documents (a label is
matched to the document with the same file name)::

    python -m course_planner.parsing_eval tests/fixtures/labels \\
        tests/fixtures/requirements tests/fixtures/messy data/samples
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from course_planner.models import ParseResult
from course_planner.parser import SUPPORTED_EXTENSIONS, parse_document

ACCEPTANCE_THRESHOLD = 0.95

Link = tuple[str, frozenset[str]]


@dataclass(frozen=True)
class CourseLabel:
    """What a person says one course in a document really contains."""

    credits: int | None
    assessments: int | None
    prerequisites: frozenset[frozenset[str]]


def load_labels(path: Path) -> dict[str, CourseLabel]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        code.upper(): CourseLabel(
            credits=entry.get("credits"),
            assessments=entry.get("assessments"),
            prerequisites=frozenset(frozenset(group) for group in entry.get("prerequisites", [])),
        )
        for code, entry in raw.items()
    }


def _ratio(correct: int, total: int, *, empty: float = 1.0) -> float:
    return correct / total if total else empty


@dataclass(frozen=True)
class DocumentScore:
    """How well one document was parsed."""

    name: str
    expected_courses: frozenset[str]
    found_courses: frozenset[str]
    expected_links: frozenset[Link]
    found_links: frozenset[Link]
    # Of the expected courses that were found: how many have the right detail.
    credits_checked: int
    credits_correct: int
    assessments_checked: int
    assessments_correct: int

    @property
    def correct_courses(self) -> frozenset[str]:
        return self.expected_courses & self.found_courses

    @property
    def correct_links(self) -> frozenset[Link]:
        return self.expected_links & self.found_links

    @property
    def missing_courses(self) -> list[str]:
        return sorted(self.expected_courses - self.found_courses)

    @property
    def extra_courses(self) -> list[str]:
        return sorted(self.found_courses - self.expected_courses)

    @property
    def missing_links(self) -> list[Link]:
        return sorted(self.expected_links - self.found_links, key=_link_key)

    @property
    def extra_links(self) -> list[Link]:
        return sorted(self.found_links - self.expected_links, key=_link_key)


def _link_key(link: Link) -> tuple[str, list[str]]:
    return link[0], sorted(link[1])


def score_document(
    name: str, result: ParseResult, labels: Mapping[str, CourseLabel]
) -> DocumentScore:
    found = result.by_code()
    expected_links = {
        (code, group) for code, label in labels.items() for group in label.prerequisites
    }
    found_links = {
        (course.code, frozenset(group))
        for course in found.values()
        for group in course.prerequisites
    }

    credits_checked = credits_correct = assessments_checked = assessments_correct = 0
    for code, label in labels.items():
        course = found.get(code)
        if course is None:
            continue
        credits_checked += 1
        credits_correct += course.credits == label.credits
        assessments_checked += 1
        assessments_correct += course.assessments == label.assessments

    return DocumentScore(
        name=name,
        expected_courses=frozenset(labels),
        found_courses=frozenset(found),
        expected_links=frozenset(expected_links),
        found_links=frozenset(found_links),
        credits_checked=credits_checked,
        credits_correct=credits_correct,
        assessments_checked=assessments_checked,
        assessments_correct=assessments_correct,
    )


@dataclass(frozen=True)
class AcceptanceReport:
    documents: tuple[DocumentScore, ...]
    threshold: float = ACCEPTANCE_THRESHOLD

    def _sum(self, attribute: str) -> int:
        return sum(len(getattr(doc, attribute)) for doc in self.documents)

    @property
    def course_recall(self) -> float:
        return _ratio(self._sum("correct_courses"), self._sum("expected_courses"))

    @property
    def course_precision(self) -> float:
        return _ratio(
            self._sum("correct_courses"),
            self._sum("found_courses"),
            empty=1.0 if not self._sum("expected_courses") else 0.0,
        )

    @property
    def link_recall(self) -> float:
        return _ratio(self._sum("correct_links"), self._sum("expected_links"))

    @property
    def link_precision(self) -> float:
        return _ratio(
            self._sum("correct_links"),
            self._sum("found_links"),
            empty=1.0 if not self._sum("expected_links") else 0.0,
        )

    @property
    def credits_accuracy(self) -> float:
        return _ratio(
            sum(d.credits_correct for d in self.documents),
            sum(d.credits_checked for d in self.documents),
        )

    @property
    def assessments_accuracy(self) -> float:
        return _ratio(
            sum(d.assessments_correct for d in self.documents),
            sum(d.assessments_checked for d in self.documents),
        )

    @property
    def passed(self) -> bool:
        return bool(self.documents) and all(
            value >= self.threshold
            for value in (
                self.course_recall,
                self.course_precision,
                self.link_recall,
                self.link_precision,
            )
        )

    def report(self) -> str:
        lines = [f"{'document':<40}{'courses':<10}{'links':<10}credits  assessments"]
        for doc in self.documents:
            lines.append(
                f"{doc.name:<40}"
                f"{len(doc.correct_courses)}/{len(doc.expected_courses):<8}"
                f"{len(doc.correct_links)}/{len(doc.expected_links):<8}"
                f"{doc.credits_correct}/{doc.credits_checked:<6}"
                f"{doc.assessments_correct}/{doc.assessments_checked}"
            )
            lines.extend(f"    missing course: {code}" for code in doc.missing_courses)
            lines.extend(f"    unexpected course: {code}" for code in doc.extra_courses)
            lines.extend(
                f"    missing link: {code} needs {' or '.join(sorted(group))}"
                for code, group in doc.missing_links
            )
            lines.extend(
                f"    unexpected link: {code} needs {' or '.join(sorted(group))}"
                for code, group in doc.extra_links
            )
        lines.append(
            f"courses: recall {self.course_recall:.1%}, precision {self.course_precision:.1%}; "
            f"prerequisite links: recall {self.link_recall:.1%}, "
            f"precision {self.link_precision:.1%}"
        )
        lines.append(
            f"(not part of the bar) credits {self.credits_accuracy:.1%}, "
            f"assessment counts {self.assessments_accuracy:.1%}"
        )
        lines.append(
            f"need {self.threshold:.0%} on all four of the first measures -> "
            f"{'PASS' if self.passed else 'FAIL'}"
        )
        return "\n".join(lines)


def find_document(stem: str, folders: Iterable[Path]) -> Path | None:
    for folder in folders:
        for suffix in SUPPORTED_EXTENSIONS:
            candidate = folder / f"{stem}{suffix}"
            if candidate.exists():
                return candidate
    return None


def evaluate_folders(labels_dir: Path, document_dirs: Sequence[Path]) -> AcceptanceReport:
    """Parse the document for every label file and score it.

    A label with no matching document is an error rather than a silent skip, so
    a mistyped folder cannot turn into a pass.
    """
    scores = []
    for label_path in sorted(labels_dir.glob("*.json")):
        document = find_document(label_path.stem, document_dirs)
        if document is None:
            raise FileNotFoundError(f"No document found for label file {label_path.name}")
        scores.append(
            score_document(document.name, parse_document(document), load_labels(label_path))
        )
    return AcceptanceReport(tuple(scores))


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print(
            "usage: python -m course_planner.parsing_eval "
            "<labels folder> <documents folder> [<documents folder> ...]"
        )
        return 2
    try:
        report = evaluate_folders(Path(args[0]), [Path(a) for a in args[1:]])
    except FileNotFoundError as exc:
        print(exc)
        return 2
    print(report.report())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
