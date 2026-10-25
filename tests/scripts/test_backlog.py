"""Guards against drift between the board and the roadmap documents.

The board has two sources of truth that must agree and cannot check each other:
each task's ``milestone:`` field, and the per-version task inventory in
``backlog/docs/plans/doc-4``. Both were edited by hand during the 0.2.0
re-scope, and a milestone that quietly loses a task - or a document that keeps a
task the board has moved - is the kind of drift no test caught before this file.

These tests read the repository as data. They never import package code, so they
run in the release-tool suite without a QGIS environment.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "backlog"
MILESTONES = BACKLOG / "milestones"
TASKS = BACKLOG / "tasks"
ROADMAP = (
    BACKLOG
    / "docs"
    / "plans"
    / "doc-4 - SemVer-delivery-roadmap-and-task-dependencies.md"
)

REQUIRED_SECTIONS = (
    "## Description and exit criteria",
    "## Deliverables by artifact",
    "## Bridge track",
    "## Version policy",
)

FENCE = re.compile(r"```.*?```", re.DOTALL)
CODE_SPAN = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
VERSION_HEADING = re.compile(r"^### (\d+\.\d+\.\d+)\s*$", re.MULTILINE)
INVENTORY_TASK = re.compile(r"\[TASK-(\d+)\]")


def frontmatter(path: Path) -> str:
    """The YAML front matter block, without its delimiters."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: no front matter"
    end = text.find("\n---\n", 4)
    assert end != -1, f"{path.name}: unterminated front matter"
    return text[4:end]


def field(path: Path, key: str) -> str | None:
    match = re.search(rf"^{key}:\s*(.+?)\s*$", frontmatter(path), re.MULTILINE)
    return match.group(1).strip('"') if match else None


def milestone_files() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(MILESTONES.glob("*.md")):
        identifier = field(path, "id")
        assert identifier, f"{path.name}: no id"
        found[identifier] = path
    return found


def milestone_versions() -> dict[str, str]:
    """milestone id -> the version its title starts with."""
    versions: dict[str, str] = {}
    for identifier, path in milestone_files().items():
        title = field(path, "title") or ""
        match = re.match(r"(\d+\.\d+\.\d+)", title)
        assert match, f"{path.name}: title does not start with a version"
        versions[identifier] = match.group(1)
    return versions


def task_assignments() -> dict[str, str]:
    """task id -> milestone id, for every non-sub-task that declares one."""
    assignments: dict[str, str] = {}
    for path in sorted(TASKS.glob("*.md")):
        identifier = field(path, "id")
        if not identifier or "." in identifier:
            continue
        milestone = field(path, "milestone")
        if milestone:
            assignments[identifier] = milestone
    return assignments


def roadmap_inventory() -> dict[str, set[str]]:
    """version -> task ids listed under that version's `###` heading."""
    text = ROADMAP.read_text(encoding="utf-8")
    headings = list(VERSION_HEADING.finditer(text))
    inventory: dict[str, set[str]] = {}
    for index, heading in enumerate(headings):
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[start:end]
        body = body.split("\n## ", 1)[0]
        inventory[heading.group(1)] = {
            f"TASK-{task}" for task in INVENTORY_TASK.findall(body)
        }
    return inventory


def test_every_task_milestone_exists() -> None:
    known = set(milestone_files())
    unknown = {
        task: milestone
        for task, milestone in task_assignments().items()
        if milestone not in known
    }
    assert not unknown, f"tasks point at unknown milestones: {unknown}"


def test_every_milestone_has_a_version_heading_in_the_roadmap() -> None:
    unlisted = set(milestone_versions().values()) - set(roadmap_inventory())
    assert not unlisted, f"milestones with no roadmap section: {sorted(unlisted)}"


def test_every_milestone_has_the_shared_sections() -> None:
    missing = {
        identifier: [
            section for section in REQUIRED_SECTIONS if section not in path.read_text()
        ]
        for identifier, path in milestone_files().items()
    }
    missing = {identifier: absent for identifier, absent in missing.items() if absent}
    assert not missing, f"milestones missing required sections: {missing}"


def test_every_milestone_documents_both_artifacts() -> None:
    """A milestone that forgets the bridge is how a pair silently desynchronises."""
    incomplete = {}
    for identifier, path in milestone_files().items():
        text = path.read_text(encoding="utf-8")
        absent = [
            artifact
            for artifact in ("`qgis-sdk`", "@archont561/qgis-sdk")
            if artifact not in text
        ]
        if absent:
            incomplete[identifier] = absent
    assert not incomplete, f"milestones not naming both artifacts: {incomplete}"


def test_every_milestone_cites_a_versioning_decision() -> None:
    stale = [
        identifier
        for identifier, path in milestone_files().items()
        if "decision-24" not in path.read_text()
        and "decision-25" not in path.read_text()
    ]
    assert not stale, f"milestones with no versioning decision: {stale}"


def test_roadmap_inventory_matches_the_board() -> None:
    """doc-4's per-version lists and each task's `milestone:` field must agree.

    This is the test that would have caught the 2026-10-24 re-scope if the
    documents had been forgotten: a task moved on the board but left behind in
    the roadmap (or the reverse) fails here.
    """
    versions = milestone_versions()
    assignments = task_assignments()
    board: dict[str, set[str]] = {}
    for task, milestone in assignments.items():
        board.setdefault(versions[milestone], set()).add(task)

    roadmap = roadmap_inventory()
    problems = []
    for version in sorted(set(board) | set(roadmap)):
        on_board = board.get(version, set())
        in_doc = roadmap.get(version, set())
        if on_board - in_doc:
            problems.append(
                f"{version}: on the board but not in doc-4: {sorted(on_board - in_doc)}"
            )
        if in_doc - on_board:
            problems.append(
                f"{version}: in doc-4 but not on the board: {sorted(in_doc - on_board)}"
            )
    assert not problems, "\n".join(problems)


def test_no_broken_relative_links() -> None:
    """A renamed record must not leave a dangling link anywhere in the backlog."""
    broken: list[str] = []
    for path in sorted(BACKLOG.rglob("*.md")):
        text = FENCE.sub("", path.read_text(encoding="utf-8"))
        text = CODE_SPAN.sub("", text)
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local = urllib.parse.unquote(target.split("#", 1)[0])
            if not local:
                continue
            if not (path.parent / local).resolve().exists():
                broken.append(f"{path.relative_to(ROOT)}: {target}")
    assert not broken, "broken links:\n" + "\n".join(broken)


@pytest.mark.parametrize("identifier", sorted(milestone_files()))
def test_milestone_exit_criteria_cover_both_packages(identifier: str) -> None:
    """Each milestone states an exit criterion per artifact, not one in general."""
    text = milestone_files()[identifier].read_text(encoding="utf-8")
    start = text.index("## Description and exit criteria")
    end = text.find("\n## ", start + 1)
    section = text[start:end]
    assert "`qgis-sdk`" in section, f"{identifier}: no Python-side exit criterion"
    assert "@archont561/qgis-sdk" in section, (
        f"{identifier}: no TypeScript-side exit criterion"
    )
