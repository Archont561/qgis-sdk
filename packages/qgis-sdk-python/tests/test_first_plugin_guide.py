"""Keep the getting-started walkthrough a single walk over working commands."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUIDE = ROOT / "apps/docs/content/docs/start/first-plugin.mdx"

#: The commands the walk runs, in the order a reader meets them. Install first,
#: then the scaffold, then the three gates, then the two host steps.
WALK = (
    "pip install qgis-sdk",
    'qgis-sdk new my_tools --title "My Tools" --no-input',
    "qgis-sdk test",
    "qgis-sdk check",
    "qgis-sdk dev",
    "qgis-sdk build",
)


def commands_in_order(text: str) -> list[str]:
    """Every command run in a fenced block, in reading order.

    Prose mentions the same commands ("`qgis-sdk dev` needs a Desktop"), so only
    the blocks a reader copies from count for the order check.
    """
    blocks = re.findall(r"^```sh\n(.*?)^```", text, re.DOTALL | re.MULTILINE)
    lines = [line.strip() for block in blocks for line in block.splitlines()]
    return [
        line for line in lines if line.startswith(("qgis-sdk ", "pip install qgis-sdk"))
    ]


def test_the_walk_runs_from_install_to_zip_in_order() -> None:
    ran = commands_in_order(GUIDE.read_text(encoding="utf-8"))
    remaining = list(ran)
    for command in WALK:
        assert command in remaining, f"{command} is missing from the walk (ran: {ran})"
        remaining = remaining[remaining.index(command) + 1 :]


def test_the_walk_does_not_send_the_reader_to_another_page() -> None:
    """The point of the page is that a reader finishes it without hopping.

    Links to other pages are allowed only in the closing section, which is what
    comes after the first plugin works. A markdown link earlier in the walk is
    the hop this page exists to remove.
    """
    guide = GUIDE.read_text(encoding="utf-8")
    closing = guide.find("## What is not on this page")
    assert closing > 0
    walk = guide[:closing]
    hops = [
        link
        for link in re.findall(r"\]\((/[^)\s]+)\)", walk)
        if not link.startswith("#")
    ]
    # The one exception is the version notice, which links to the matrix by design.
    assert [link for link in hops if link != "/python/supported-targets/"] == []


def test_documented_scaffold_commands_match_the_generated_files(tmp_path: Path) -> None:
    import shlex

    from qgis_sdk_tools.__main__ import app
    from typer.testing import CliRunner

    guide = GUIDE.read_text(encoding="utf-8")
    commands = re.findall(r"^qgis-sdk new my_tools[^\n]*$", guide, re.MULTILINE)
    assert commands == [
        'qgis-sdk new my_tools --title "My Tools" --no-input',
        'qgis-sdk new my_tools --title "My Tools" --ui native --no-input',
        'qgis-sdk new my_tools --title "My Tools" --web vanilla --no-input --no-install',
    ]
    runner = CliRunner()
    for index, command in enumerate(commands):
        root = tmp_path / str(index)
        root.mkdir()
        project = root / "my_tools"
        args = shlex.split(command)[1:]
        args[1] = str(project)
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert (project / "pyproject.toml").is_file()
        assert (project / "my_tools/plugin.py").is_file()
        assert (project / "tests/test_plugin.py").is_file()
        assert (project / "my_tools/ui.py").is_file() == (index == 1)
        assert not (project / "my_tools/surfaces.py").exists()
        assert (project / "web/src/bridge.schema.ts").is_file() == (index == 2)
