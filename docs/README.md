# Project webpage

`index.html` is the project page for AILT9019 Group 36. It is plain HTML, CSS and JavaScript with no build step.
Publish it with GitHub Pages: Settings > Pages > Deploy from a branch > `main` / `/docs`.

- `plan-data.js` holds the real run behind the page's 8-semester board (`data/samples/cs_route_8_semesters.txt`) and is generated, not hand-edited.
  Regenerate it after changing the parser, scoring or planner: `python docs/build_plan_data.py`.
- `assets/` holds screenshots of the running app.
- The recorded demo is embedded through `VIDEO_ID` near the end of `index.html` (currently `zb94ASuKkm8`). The presentation video is linked in the page footer and under the demo.
- The evidence chart's numbers come from `python -m course_planner.evaluation tests/fixtures/requirements`.
