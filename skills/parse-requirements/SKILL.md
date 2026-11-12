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
Some files hold several degrees (for example one syllabus each for Computer, Electrical and
Electronic Engineering). The first is read by default; add `--programme "NAME"` to read
another one, using a name from the `programmes` list in the output.

Only `.pdf`, `.txt` and `.csv` files are accepted. Plain text and CSV need nothing
installed; PDF needs `pdfplumber`. If it is missing, try `pip install pdfplumber`, and if
that is not possible, ask the user to paste the text or upload a CSV instead.

## Output

JSON, for example:

```json
{"courses": [{"code": "COMP2119", "title": "...", "credits": 6, "assessments": 5,
              "elective": false,
              "prerequisites": [["COMP1117"], ["MATH1013", "MATH1853"]]}],
 "warnings": ["COMP3314: credits were not found in the document."],
 "programmes": [], "programme": ""}
```

`elective` is true for courses the student chooses from a list ("electives", "choose one of",
courses that appear only in a catalogue of a document that also has requirement tables); false
means required, or that the document does not say.

`prerequisites` is an AND of OR-groups: every inner list needs at least one of its courses
completed. The example reads "COMP1117 and (MATH1013 or MATH1853)". `A or (B and C)` is given
in the same form as `[[A, B], [A, C]]`.

`programmes` lists the degrees found when a file holds several (empty otherwise), and
`programme` is the one the `courses` were read for.

## Rules

- Exit code 1 with `{"error": ...}` means the file was unreadable (scanned PDF, wrong type)
  or contained no courses. Report the message; never invent courses.
- Always show the user the `warnings`. A null `credits` or `assessments` means the document
  did not say, not zero.
- Only course codes like `COMP1117` count as prerequisites. Year-standing, exam-grade or
  approval conditions cannot be checked, so they are left out and reported in `warnings`;
  tell the user if the source mentions them.
- This is a draft aid, not an official graduation audit.
