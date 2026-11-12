"""Read an uploaded document for the app, with fallbacks and plain-language messages."""

from __future__ import annotations

from course_planner.models import ParseResult
from course_planner.parser import EmptyDocumentError, UnsupportedFileError, parse_document
from course_planner.storage import DocumentStore

# (level, message); level is one of "error", "warning", "info".
Notice = tuple[str, str]


def read_document(
    data: bytes, name: str, store: DocumentStore, programme: str | None = None
) -> tuple[ParseResult | None, list[Notice]]:
    """Parse ``data``; returns ``(result, notices)`` where ``result`` is ``None`` on failure.

    Fallbacks, in order:

    * a file that cannot be read (damaged PDF, scanned image, unexpected error)
      uses the saved result for the exact same bytes, if one exists;
    * otherwise the student gets a message saying what went wrong and what to try.

    An unsupported file type never falls back: it is rejected outright. ``programme`` picks one
    degree when the document contains several.
    """
    try:
        result = parse_document(data, name, programme)
    except UnsupportedFileError as exc:
        return None, [("error", str(exc))]
    except Exception as exc:  # EmptyDocumentError, or anything unexpected from a PDF library
        reason = (
            str(exc)
            if isinstance(exc, EmptyDocumentError)
            else "Something went wrong while reading this file."
        )
        cached = _load_cached(store, data)
        if cached is not None:
            return cached, [
                (
                    "warning",
                    f"{reason} Showing the saved result from the last time this exact "
                    "document was read.",
                )
            ]
        hint = "Try pasting the text instead, or upload a CSV with a 'code' column."
        return None, [("error", f"{reason} {hint}")]

    if not result.courses:
        detail = " ".join(result.warnings)
        return None, [
            (
                "error",
                f"No courses were found. {detail} Check that course codes look like "
                "COMP1117, or upload a CSV instead.",
            )
        ]

    notices: list[Notice] = []
    try:
        store.save(name, data, result)
    except Exception:
        notices.append(("warning", "The result could not be saved on this computer."))
    return result, notices


def _load_cached(store: DocumentStore, data: bytes) -> ParseResult | None:
    try:
        return store.load_parsed(data)
    except Exception:
        return None
