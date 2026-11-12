---
name: parse-requirements
description: Extract courses, credits, assessment counts and prerequisites from a programme requirement document (PDF, .txt or .csv) into JSON. Use for course requirement lists, syllabi or curriculum pages.
---

# Parse a programme requirement document

Runs the HKU Course Planner (AILT9019 Group 36) parser. It works offline and stores nothing.

## Run

From this skill's folder, with the user's file path:

```bash
python3 scripts/parse_requirements.py path/to/requirements.pdf
```

(In Claude Code you can write the script path as `${CLAUDE_SKILL_DIR}/scripts/parse_requirements.py`.)
Only `.pdf`, `.txt` and `.csv` files are accepted. Plain text and CSV need nothing
installed; PDF needs `pdfplumber`. If it is missing, try `pip install pdfplumber`, and if
that is not possible, ask the user to paste the text or upload a CSV instead.

## Output

JSON, for example:

```json
{"courses": [{"code": "COMP2119", "title": "...", "credits": 6, "assessments": 5,
              "prerequisites": [["COMP1117"], ["MATH1013", "MATH1853"]]}],
 "warnings": ["COMP3314: credits were not found in the document."]}
```

`prerequisites` is an AND of OR-groups: every inner list needs at least one of its courses
completed. The example reads "COMP1117 and (MATH1013 or MATH1853)".

## Rules

- Exit code 1 with `{"error": ...}` means the file was unreadable (scanned PDF, wrong type)
  or contained no courses. Report the message; never invent courses.
- Always show the user the `warnings`. A null `credits` or `assessments` means the document
  did not say, not zero.
- Only course codes like `COMP1117` count as prerequisites. Year-standing or approval
  conditions are ignored; tell the user if the source mentions them.
- This is a draft aid, not an official graduation audit.
