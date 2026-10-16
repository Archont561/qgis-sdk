from __future__ import annotations

from pathlib import Path

import pytest
from scripts.quick_validate import validate_skill


def test_skill_validator_rejects_description_with_markup(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Use <demo> markup.\n---\n",
        encoding="utf-8",
    )

    valid, message = validate_skill(tmp_path)

    assert valid is False
    assert "angle brackets" in message


@pytest.mark.parametrize(
    ("frontmatter", "expected_message"),
    [
        (
            "name: demo-skill\ndescription: Use the skill.\nunexpected: true",
            "Unexpected key(s)",
        ),
        ("description: Use the skill.", "Missing 'name'"),
        (
            "name: BadName\ndescription: Use the skill.",
            "should be kebab-case",
        ),
        (
            "name: demo-skill\ndescription: 123",
            "Description must be a string",
        ),
        (
            "name: demo-skill\ndescription: Use the skill.\ncompatibility: 123",
            "Compatibility must be a string",
        ),
    ],
)
def test_skill_validator_preserves_frontmatter_error_messages(
    tmp_path: Path, frontmatter: str, expected_message: str
) -> None:
    (tmp_path / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n", encoding="utf-8")

    valid, message = validate_skill(tmp_path)

    assert valid is False
    assert expected_message in message
