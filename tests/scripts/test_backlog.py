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


def _record_ids_are_unique_phase1(declared):
    clashes = {
        identifier: paths for identifier, paths in declared.items() if len(paths) > 1
    }
    assert not clashes, "duplicate record ids:\n" + "\n".join(
        f"{identifier}: "
        + ", ".join(path.relative_to(ROOT).as_posix() for path in paths)
        for identifier, paths in sorted(clashes.items())
    )


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


GATE_TITLE = re.compile(r"^Prepare and qualify (\d+\.\d+\.\d+) release")
DEFERRAL = re.compile(r"^\*\*Deferred[^\n]*\*\*[^\n]*\S", re.MULTILINE)
STATUS_KEY = "status"

SHIPPED = "Done"


def task_statuses() -> dict[str, str]:
    """task id -> its ``status`` field."""
    statuses: dict[str, str] = {}
    for path in sorted(TASKS.glob("*.md")):
        identifier = field(path, "id")
        status = field(path, STATUS_KEY)
        if identifier and status:
            statuses[identifier] = status
    return statuses


def gate_tasks() -> dict[str, str]:
    """milestone version -> the id of the task that gates that release.

    Each milestone names its gate in its exit criteria ("released at 0.11.0
    from one green gate (TASK-95)"); the gate's own title carries the version,
    so the pair is found without reading prose.
    """
    gates: dict[str, str] = {}
    for path in sorted(TASKS.glob("*.md")):
        title = " ".join((field(path, "title") or "").split())
        match = GATE_TITLE.match(title)
        identifier = field(path, "id")
        if match and identifier:
            gates[match.group(1)] = identifier
    return gates


def shipped_milestones() -> dict[str, str]:
    """milestone id -> version, for the milestones whose release gate is Done."""
    statuses = task_statuses()
    gates = gate_tasks()
    versions = milestone_versions()
    return {
        identifier: version
        for identifier, version in versions.items()
        if statuses.get(gates.get(version, ""), "") == SHIPPED
    }


def test_a_shipped_milestone_has_no_open_task_without_a_deferral() -> None:
    """Shipped work is `Done`, or its record says why it is not.

    TASK-102 is the shape this allows: its behaviour shipped in 0.10.0 and one
    criterion asks for a measurement that was never taken, so the task stays
    open and its note begins `**Deferred`. Anything else is drift - work that
    landed while the board still lists it as outstanding.
    """
    statuses = task_statuses()
    assignments = task_assignments()
    shipped = shipped_milestones()
    problems = []
    for identifier, milestone in sorted(assignments.items()):
        if milestone not in shipped or statuses.get(identifier, SHIPPED) == SHIPPED:
            continue
        text = next(TASKS.glob(f"task-{identifier.removeprefix('TASK-')} *.md"), None)
        body = text.read_text(encoding="utf-8") if text else ""
        if not DEFERRAL.search(body):
            problems.append(
                f"{identifier} is {statuses[identifier]} in shipped "
                f"{shipped[milestone]} with no **Deferred note"
            )
    assert problems == [], "open tasks in shipped milestones:\n" + "\n".join(problems)


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


COVERAGE_MAP = BACKLOG / "docs" / "plans" / "doc-22 - Service-coverage-map.md"
ROW_TASK = re.compile(r"\[TASK-(\d+)\]")


def coverage_map_section(name: str) -> str:
    text = COVERAGE_MAP.read_text(encoding="utf-8")
    assert f"## {name}" in text, f"doc-22 has no '## {name}' section"
    return text.split(f"## {name}", 1)[1].split("\n## ", 1)[0]


def coverage_map_rows(name: str) -> list[list[str]]:
    """The body rows of the tables in one section, cells stripped."""
    rows: list[list[str]] = []
    for line in coverage_map_section(name).splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(set(cell) <= set(":- ") for cell in cells):
            continue  # the `| --- |` separator
        if cells[0] in {"Area", "Task"}:
            continue  # the header
        rows.append(cells)
    return rows


def first_task(row: list[str]) -> str | None:
    """The task a row is *about*: the first one it links."""
    for cell in row:
        match = ROW_TASK.search(cell)
        if match:
            return f"TASK-{match.group(1)}"
    return None


@pytest.mark.parametrize("section", ["Planned", "Proposals awaiting a decision"])
def test_a_row_that_claims_open_work_names_an_open_task(section: str) -> None:
    """`Planned` and `Proposals` are open work; their first task may not be Done.

    A proposal closes by becoming a decision or a shipped row, and a planned row
    closes by moving to *Shipped* - never by staying where it is once the board
    says the work is finished. TASK-159 sat in *Proposals awaiting a decision*
    for a day after it shipped, which is the drift this catches: the map is the
    1.0 gate's source of truth (decision-54 point 5), so a finished row left in
    the open lists overstates what is left to do.
    """
    statuses = task_statuses()
    finished = []
    for row in coverage_map_rows(section):
        if section == "Planned" and not row[-1].lower().startswith("planned"):
            continue
        task = first_task(row)
        if task is not None and statuses.get(task) == SHIPPED:
            finished.append(f"{row[0]}: {task} is {SHIPPED}")
    assert not finished, (
        "doc-22 lists finished work as outstanding in "
        f"'## {section}':\n" + "\n".join(finished)
    )


def test_every_task_the_coverage_map_cites_exists() -> None:
    """A cited id that no record answers is a row nobody can follow."""
    cited = {
        f"TASK-{number}"
        for number in re.findall(
            r"TASK-(\d+)", COVERAGE_MAP.read_text(encoding="utf-8")
        )
    }
    missing = sorted(cited - set(task_statuses()))
    assert not missing, f"doc-22 cites {', '.join(missing)}, which the board lacks"


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


def test_record_ids_are_unique() -> None:
    """Two records may not answer to the same id.

    Document numbers are allocated in creation order by hand, so a new plan can
    take a number another plan already holds - which is what happened when the
    coverage review was written as ``doc-27`` while ``doc-27`` was the m-11
    sprint train. Nothing else notices: the files have different names, the
    front matter is well formed, and a link naming either id resolves to whichever
    record the reader lands on. `backlog doctor` reports this, but it is not run
    on every change.
    """
    declared: dict[str, list[Path]] = {}
    for path in sorted(BACKLOG.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---\n", 4)
        if end == -1:
            continue
        match = re.search(r"^id:\s*(\S+)\s*$", text[4:end], re.MULTILINE)
        if match is None:
            continue
        declared.setdefault(match.group(1), []).append(path)

    _record_ids_are_unique_phase1(declared)


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
