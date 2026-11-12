"""Keep the getting-started walkthrough a single walk over working commands."""

from __future__ import annotations

import copy
import re
from pathlib import Path


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_test_documented__p1(_s):
    import shlex

    _s.shlex = shlex

    from qgis_sdk_tools.__main__ import app

    _s.app = app
    from typer.testing import CliRunner

    _s.CliRunner = CliRunner

    _s.guide = GUIDE.read_text(encoding="utf-8")
    _s.commands = re.findall(r"^qgis-sdk new my_tools[^\n]*$", _s.guide, re.MULTILINE)
    assert _s.commands == _cc_fresh_1()
    _s.runner = _s.CliRunner()


def _cc_test_documented__p2(_s):
    for index, command in enumerate(_s.commands):
        _s.index = index
        _s.command = command
        _s.root = _s.tmp_path / str(_s.index)
        _s.root.mkdir()
        _s.project = _s.root / "my_tools"
        _s.args = _s.shlex.split(_s.command)[1:]
        _s.args[1] = str(_s.project)
        _s.result = _s.runner.invoke(_s.app, _s.args)
        assert _s.result.exit_code == 0, _s.result.output
        assert (_s.project / "pyproject.toml").is_file()
        assert (_s.project / "my_tools/plugin.py").is_file()
        assert (_s.project / "tests/test_plugin.py").is_file()
        assert (_s.project / "my_tools/ui.py").is_file() == (_s.index == 1)
        assert not (_s.project / "my_tools/surfaces.py").exists()
        assert (_s.project / "web/src/bridge.schema.ts").is_file() == (_s.index == 2)


_CC_DATA_1 = [
    'qgis-sdk new my_tools --title "My Tools" --no-input',
    'qgis-sdk new my_tools --title "My Tools" --ui native --no-input',
    'qgis-sdk new my_tools --title "My Tools" --web vanilla --no-input --no-install',
]


def _cc_fresh_1():
    """Return a fresh copy of the shared data literal."""
    return copy.deepcopy(_CC_DATA_1)


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
    _s = _CcState(tmp_path=tmp_path)
    for _p in (_cc_test_documented__p1, _cc_test_documented__p2):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
