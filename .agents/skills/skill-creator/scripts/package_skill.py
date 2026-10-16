#!/usr/bin/env python3
"""
Skill Packager - Creates a distributable .skill file of a skill folder

Usage:
    python utils/package_skill.py <path/to/skill-folder> [output-directory]

Example:
    python utils/package_skill.py skills/public/my-skill
    python utils/package_skill.py skills/public/my-skill ./dist
"""

import fnmatch
import sys
import zipfile
from pathlib import Path

from scripts.quick_validate import validate_skill

# Patterns to exclude when packaging skills.
EXCLUDE_DIRS = {"__pycache__", "node_modules"}
EXCLUDE_GLOBS = {"*.pyc"}
EXCLUDE_FILES = {".DS_Store"}
# Directories excluded only at the skill root (not when nested deeper).
ROOT_EXCLUDE_DIRS = {"evals"}


def should_exclude(rel_path: Path) -> bool:
    """Check if a path should be excluded from packaging."""
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    # rel_path is relative to skill_path.parent, so parts[0] is the skill
    # folder name and parts[1] (if present) is the first subdir.
    if len(parts) > 1 and parts[1] in ROOT_EXCLUDE_DIRS:
        return True
    name = rel_path.name
    if name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_GLOBS)


def _validate_skill(skill_path: Path) -> bool:
    if not skill_path.exists():
        print(f"❌ Error: Skill folder not found: {skill_path}")
        return False
    if not skill_path.is_dir():
        print(f"❌ Error: Path is not a directory: {skill_path}")
        return False
    if not (skill_path / "SKILL.md").exists():
        print(f"❌ Error: SKILL.md not found in {skill_path}")
        return False

    print("🔍 Validating skill...")
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"❌ Validation failed: {message}")
        print("   Please fix the validation errors before packaging.")
        return False
    print(f"✅ {message}\n")
    return True


def _resolve_output_path(skill_path: Path, output_dir: str | Path | None) -> Path:
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path / f"{skill_path.name}.skill"
    return Path.cwd() / f"{skill_path.name}.skill"


def _write_skill_archive(skill_path: Path, skill_filename: Path) -> Path | None:
    try:
        with zipfile.ZipFile(skill_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in skill_path.rglob("*"):
                if not file_path.is_file():
                    continue
                arcname = file_path.relative_to(skill_path.parent)
                if should_exclude(arcname):
                    print(f"  Skipped: {arcname}")
                    continue
                zipf.write(file_path, arcname)
                print(f"  Added: {arcname}")

        print(f"\n✅ Successfully packaged skill to: {skill_filename}")
        return skill_filename
    except (OSError, ValueError, zipfile.LargeZipFile) as error:
        print(f"❌ Error creating .skill file: {error}")
        return None


def package_skill(
    skill_path: str | Path, output_dir: str | Path | None = None
) -> Path | None:
    """Validate and package a skill folder into a distributable .skill archive."""
    resolved_skill_path = Path(skill_path).resolve()
    if not _validate_skill(resolved_skill_path):
        return None
    skill_filename = _resolve_output_path(resolved_skill_path, output_dir)
    return _write_skill_archive(resolved_skill_path, skill_filename)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python utils/package_skill.py <path/to/skill-folder> [output-directory]"
        )
        print("\nExample:")
        print("  python utils/package_skill.py skills/public/my-skill")
        print("  python utils/package_skill.py skills/public/my-skill ./dist")
        sys.exit(1)

    skill_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"📦 Packaging skill: {skill_path}")
    if output_dir:
        print(f"   Output directory: {output_dir}")
    print()

    result = package_skill(skill_path, output_dir)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
