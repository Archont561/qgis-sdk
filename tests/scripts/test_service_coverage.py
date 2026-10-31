"""doc-22 is the source of truth for what the host maps (decision-54 point 5).

The coverage map answers "what is covered" for the 1.0 gate, so it has to be
complete in both directions: an operation the host answers but the map does not
list is a service that shipped without a row, and a row whose operation no
longer exists is a map that argues for something the code stopped doing. Both
are failures here rather than something a reader has to notice.

The declaration is imported rather than copied, so the check follows the code:
``HOST_OPERATIONS`` is where an operation is added.
"""

from __future__ import annotations

import re
from pathlib import Path

from qgis_sdk.bridge.host import HOST_OPERATIONS, host_grant_names

ROOT = Path(__file__).resolve().parents[2]
COVERAGE_MAP = ROOT / "backlog" / "docs" / "plans" / "doc-22 - Service-coverage-map.md"

#: A row of the "Host operations" table: a backticked `<service>.<operation>`.
_ROW = re.compile(
    r"^\| `(?P<operation>[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*)` \|", re.MULTILINE
)


def _section() -> str:
    text = COVERAGE_MAP.read_text(encoding="utf-8")
    assert "## Host operations" in text, (
        "doc-22 has no '## Host operations' section; the coverage map is the "
        "source of truth (decision-54 point 5)"
    )
    return text.split("## Host operations", 1)[1].split("\n## ", 1)[0]


def _documented() -> dict[str, int]:
    """Every documented operation, mapped to how many rows name it."""
    counts: dict[str, int] = {}
    for match in _ROW.finditer(_section()):
        operation = match.group("operation")
        counts[operation] = counts.get(operation, 0) + 1
    return counts


def test_every_host_operation_has_a_row_in_the_coverage_map() -> None:
    documented = _documented()
    missing = [
        operation.id for operation in HOST_OPERATIONS if operation.id not in documented
    ]

    assert not missing, (
        f"doc-22 does not list {', '.join(missing)}; add a row per operation to "
        "'## Host operations' in the same change that declares it"
    )


def test_the_coverage_map_names_no_operation_the_host_does_not_answer() -> None:
    declared = {operation.id for operation in HOST_OPERATIONS}
    stale = sorted(set(_documented()) - declared)

    assert not stale, (
        f"doc-22 lists {', '.join(stale)}, which qgis_sdk.bridge.host no longer "
        "declares; remove the row or restore the operation"
    )


def test_no_operation_is_listed_twice() -> None:
    repeated = sorted(op for op, count in _documented().items() if count > 1)

    assert not repeated, f"doc-22 lists {', '.join(repeated)} more than once"


def test_every_grant_name_appears_in_the_map() -> None:
    section = _section()
    missing = [grant for grant in host_grant_names() if f"`{grant}`" not in section]

    assert not missing, (
        f"doc-22 does not name the grant(s) {', '.join(missing)}; the grant "
        "column is where the shared vocabulary is visible"
    )


def test_the_map_points_at_the_checks_that_keep_it_honest() -> None:
    section = _section()

    assert "qgis-sdk check --grants" in section
    assert "test_service_coverage.py" in section
