#!/usr/bin/env python3
"""Quick validation script for skill frontmatter."""

import re
import sys
from pathlib import Path

import yaml

ALLOWED_PROPERTIES = frozenset(
    {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
)


def _parse_frontmatter(
    skill_md: Path,
) -> tuple[dict[object, object] | None, str | None]:
    content = skill_md.read_text()
    if not content.startswith("---"):
        return None, "No YAML frontmatter found"

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None, "Invalid frontmatter format"

    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        return None, f"Invalid YAML in frontmatter: {error}"
    if not isinstance(frontmatter, dict):
        return None, "Frontmatter must be a YAML dictionary"
    return frontmatter, None


def _validate_declared_properties(frontmatter: dict[object, object]) -> str | None:
    unexpected_keys = set(frontmatter) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )
    if "name" not in frontmatter:
        return "Missing 'name' in frontmatter"
    if "description" not in frontmatter:
        return "Missing 'description' in frontmatter"
    return None


def _validate_name(frontmatter: dict[object, object]) -> str | None:
    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        if not re.match(r"^[a-z0-9-]+$", name):
            return f"Name '{name}' should be kebab-case (lowercase letters, digits, and hyphens only)"
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
        if len(name) > 64:
            return (
                f"Name is too long ({len(name)} characters). Maximum is 64 characters."
            )
    return None


def _validate_description(frontmatter: dict[object, object]) -> str | None:
    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if description:
        if "<" in description or ">" in description:
            return "Description cannot contain angle brackets (< or >)"
        if len(description) > 1024:
            return f"Description is too long ({len(description)} characters). Maximum is 1024 characters."
    return None


def _validate_compatibility(frontmatter: dict[object, object]) -> str | None:
    compatibility = frontmatter.get("compatibility", "")
    if compatibility:
        if not isinstance(compatibility, str):
            return f"Compatibility must be a string, got {type(compatibility).__name__}"
        if len(compatibility) > 500:
            return f"Compatibility is too long ({len(compatibility)} characters). Maximum is 500 characters."
    return None


def _validate_frontmatter(frontmatter: dict[object, object]) -> str | None:
    for validator in (
        _validate_declared_properties,
        _validate_name,
        _validate_description,
        _validate_compatibility,
    ):
        message = validator(frontmatter)
        if message:
            return message
    return None


def validate_skill(skill_path: str | Path) -> tuple[bool, str]:
    """Validate the required fields and constraints in a skill's frontmatter."""
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    frontmatter, parse_error = _parse_frontmatter(skill_md)
    if parse_error:
        return False, parse_error
    if frontmatter is None:
        return False, "Frontmatter must be a YAML dictionary"

    validation_error = _validate_frontmatter(frontmatter)
    if validation_error:
        return False, validation_error
    return True, "Skill is valid!"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
