"""A tiny PDF writer so tests can run the real PDF path without extra dependencies."""

from __future__ import annotations


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(text: str, lines_per_page: int = 60) -> bytes:
    """Return a text-only PDF with ``text`` set in Helvetica, one source line per line."""
    lines = text.splitlines()
    pages = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[]]

    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, page_lines in enumerate(pages):
        operations = ["BT", "/F1 9 Tf", "12 TL", "30 810 Td"]
        operations += [f"({_escape(line)}) Tj T*" for line in page_lines]
        operations.append("ET")
        stream = "\n".join(operations).encode("latin-1", "replace")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1400 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)
