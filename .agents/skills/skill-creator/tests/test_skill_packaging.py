from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.package_skill import package_skill
from scripts.quick_validate import validate_skill


def test_skill_validator_accepts_valid_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Use this skill for useful demos.\n---\n",
        encoding="utf-8",
    )

    assert validate_skill(tmp_path) == (True, "Skill is valid!")


def test_packager_writes_validated_skill_and_excludes_root_evals(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "demo-skill"
    evals_dir = skill_dir / "evals"
    evals_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Use this skill for useful demos.\n---\n",
        encoding="utf-8",
    )
    (skill_dir / "README.md").write_text("Documentation", encoding="utf-8")
    (evals_dir / "cases.json").write_text("[]", encoding="utf-8")

    archive_path = package_skill(skill_dir, tmp_path / "dist")

    assert archive_path == tmp_path / "dist" / "demo-skill.skill"
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {
            "demo-skill/SKILL.md",
            "demo-skill/README.md",
        }
