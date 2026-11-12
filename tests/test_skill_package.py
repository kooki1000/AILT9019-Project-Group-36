import importlib.util
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
SAMPLE = ROOT / "data" / "samples" / "sample_requirements.txt"

_spec = importlib.util.spec_from_file_location("build_skill", ROOT / "skills" / "build_skill.py")
build_skill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_skill)


def frontmatter(text: str) -> dict[str, str]:
    block = re.match(r"---\n(.*?)\n---\n", text, re.S).group(1)
    return dict(line.split(": ", 1) for line in block.splitlines())


def test_skill_metadata_fits_both_vendors():
    meta = frontmatter((ROOT / "skills" / "parse-requirements" / "SKILL.md").read_text())
    assert set(meta) == {"name", "description"}
    assert meta["name"] == "parse-requirements"
    assert re.fullmatch(r"[a-z0-9-]{1,64}", meta["name"])
    assert len(meta["description"]) <= 200  # claude.ai's limit; the spec allows 1024


def test_zip_has_the_skill_folder_at_its_top_level(tmp_path):
    archive = build_skill.build(tmp_path / "skill.zip")
    names = zipfile.ZipFile(archive).namelist()
    assert "parse-requirements/SKILL.md" in names
    assert all(n.startswith("parse-requirements/") for n in names)
    assert "parse-requirements/scripts/parse_requirements.py" in names


def test_bundled_modules_are_exact_copies_of_the_source(tmp_path):
    archive = zipfile.ZipFile(build_skill.build(tmp_path / "skill.zip"))
    for module in build_skill.BUNDLED_MODULES:
        bundled = archive.read(f"parse-requirements/scripts/course_planner/{module}")
        assert bundled == (ROOT / "src" / "course_planner" / module).read_bytes()


def test_unzipped_skill_runs_on_its_own(tmp_path):
    zipfile.ZipFile(build_skill.build(tmp_path / "skill.zip")).extractall(tmp_path / "out")
    script = tmp_path / "out" / "parse-requirements" / "scripts" / "parse_requirements.py"
    done = subprocess.run(
        [sys.executable, str(script), str(SAMPLE)],
        capture_output=True, text=True, cwd=tmp_path, check=False,
    )
    assert done.returncode == 0, done.stderr
    assert len(json.loads(done.stdout)["courses"]) == 7
