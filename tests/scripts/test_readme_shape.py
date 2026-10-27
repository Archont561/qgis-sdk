"""Keeps every README in the landing-page shape decision-29 settled on.

A README carries a pitch, a status line, installation, one example, pointers
and the license - and nothing that explains, qualifies or records evidence.
That prose belongs in ``backlog/docs/guides/`` until the documentation site
(TASK-43) renders it. The old shape crept in one section at a time, each task
appending the paragraph that proved its acceptance criteria, so the guard is a
closed set of allowed section headings and a line budget rather than a review
habit.

These tests read the repository as data and import no package code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

READMES = (
    ROOT / "README.md",
    ROOT / "packages" / "qgis-sdk-python" / "README.md",
    ROOT / "packages" / "qgis-sdk-runtime" / "README.md",
    ROOT / "packages" / "qgis-sdk-tools" / "README.md",
    ROOT / "packages" / "qgis-sdk-typescript" / "README.md",
    ROOT / "packages" / "qgis-sdk-ui" / "README.md",
    ROOT / "packages" / "qgis-sdk-alias" / "README.md",
    ROOT / "packages" / "qgis-sdk-ui-alias" / "README.md",
    ROOT / "packages" / "config" / "README.md",
    ROOT / "examples" / "simple" / "README.md",
)

# The two unscoped aliases are one README: the same words with the names
# swapped. Only the `## Example` section (the entry points differ) may diverge.
EXAMPLE_SECTION = re.compile(r"## Example\n.*?(?=\n## )", re.DOTALL)
ALIASES = (
    (
        ROOT / "packages" / "qgis-sdk-alias" / "README.md",
        "qgis-sdk",
        "qgis-sdk-typescript",
    ),
    (
        ROOT / "packages" / "qgis-sdk-ui-alias" / "README.md",
        "qgis-sdk-ui",
        "qgis-sdk-ui",
    ),
)

# The only sections a landing page may have. A new kind of section is a
# decision, not an edit: amend decision-29 and this set together.
ALLOWED_SECTIONS = frozenset(
    {
        "Installation",
        "Try it",
        "Example",
        "Develop",
        "Documentation",
        "License",
    }
)

MAX_LINES = 80

FENCE = re.compile(r"```.*?```", re.DOTALL)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
GUIDES = ROOT / "backlog" / "docs" / "guides"


def _prose(path: Path) -> str:
    """The README without its fenced code, so a ``#`` comment is not a heading."""
    return FENCE.sub("", path.read_text(encoding="utf-8"))


def _headings(path: Path) -> list[tuple[int, str]]:
    return [(len(hashes), title) for hashes, title in HEADING.findall(_prose(path))]


@pytest.mark.parametrize("path", READMES, ids=lambda p: str(p.relative_to(ROOT)))
def test_a_readme_has_one_title_and_only_landing_page_sections(path: Path) -> None:
    headings = _headings(path)
    titles = [title for level, title in headings if level == 1]
    assert len(titles) == 1, f"{path.name}: one H1, found {titles}"
    sections = [title for level, title in headings if level == 2]
    unexpected = sorted(set(sections) - ALLOWED_SECTIONS)
    assert not unexpected, (
        f"{path.relative_to(ROOT)} grew a section outside the decision-29 shape: "
        f"{unexpected}. Reference prose goes in backlog/docs/guides/."
    )
    deeper = [title for level, title in headings if level >= 3]
    assert not deeper, f"{path.name}: a landing page has no subsections, found {deeper}"


@pytest.mark.parametrize("path", READMES, ids=lambda p: str(p.relative_to(ROOT)))
def test_a_readme_stays_within_the_line_budget(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").count("\n")
    assert lines <= MAX_LINES, (
        f"{path.relative_to(ROOT)} is {lines} lines; the budget is {MAX_LINES}. "
        "Move the detail to a guide and link to it."
    )


@pytest.mark.parametrize("path", READMES, ids=lambda p: str(p.relative_to(ROOT)))
def test_a_readme_carries_a_status_line_and_a_license(path: Path) -> None:
    """The landing-page fields every README has, in the order decision-29 gives."""
    text = path.read_text(encoding="utf-8")
    assert "\n> Status:" in text, f"{path.name}: no `> Status:` line"
    assert text.rstrip().endswith("## License\n\nMIT"), f"{path.name}: License last"
    assert text.index("> Status:") < text.index("## ")


def test_the_two_aliases_share_one_readme() -> None:
    """Same prose, names swapped; only the `## Example` section may differ."""
    normalised = []
    for path, alias, scoped_dir in ALIASES:
        text = EXAMPLE_SECTION.sub("## Example", path.read_text(encoding="utf-8"))
        text = text.replace("Archont561/qgis-sdk/", "<repo>/")  # the repository
        text = text.replace("%20qgis-sdk-", "%20<kit>-")  # the guides' file names
        text = text.replace(f"packages/{scoped_dir}", "packages/<scoped-dir>")
        text = text.replace(f"@archont561/{alias}", "<scoped>").replace(
            alias, "<alias>"
        )
        normalised.append(text)
    assert normalised[0] == normalised[1]


@pytest.mark.parametrize("path", READMES, ids=lambda p: str(p.relative_to(ROOT)))
def test_a_published_readme_points_at_the_guides(path: Path) -> None:
    """The READMEs that are landing pages link to where the prose went."""
    text = path.read_text(encoding="utf-8")
    assert "## Documentation" in text, f"{path.name}: no Documentation section"
    guides = sorted(p.name for p in GUIDES.glob("doc-*.md"))
    assert guides, "backlog/docs/guides/ is empty"
    linked = [name for name in guides if name.replace(" ", "%20") in text]
    assert linked, f"{path.name} links none of {guides}"
