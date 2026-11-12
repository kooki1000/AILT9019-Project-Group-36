---
name: parse-requirements
description: Extract courses, credits, assessment counts and prerequisites from a programme requirement document (PDF, plain text or CSV) into JSON. Use when asked to read a course requirement list, syllabus or curriculum page and list what must be taken and in what dependency order.
---

# Parse a programme requirement document

Runs the HKU Course Planner (AILT9019 Group 36) parser locally. Nothing is uploaded or stored.

## Setup (once)

From the repository root: `pip install -e .` (needs Python 3.10+).

## Use

```bash
python -m course_planner.parse_cli path/to/requirements.pdf
```

Accepts `.pdf`, `.txt` and `.csv` only. Output is JSON:

```json
{"courses": [{"code": "COMP2119", "title": "...", "credits": 6, "assessments": 5,
              "prerequisites": [["COMP1117"], ["MATH1013", "MATH1853"]]}],
 "warnings": ["COMP3314: credits were not found in the document."]}
```

`prerequisites` is an AND of OR-groups: every inner list needs at least one of its
courses completed. The example reads "COMP1117 and (MATH1013 or MATH1853)".

## Rules

- Exit code 1 with `{"error": ...}` means the file was unreadable (scanned PDF, wrong
  type) or had no courses. Report the message; do not invent courses.
- Always show the user the `warnings`. A null `credits` or `assessments` means the
  document did not say, not zero.
- Only course codes like `COMP1117` are recognised as prerequisites. Year-standing or
  approval conditions are ignored; tell the user if the source mentions them.
- This is a draft aid, not an official graduation audit.
