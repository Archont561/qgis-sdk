"""Keep the getting-started walkthrough tied to the working reference plugin."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUIDE = ROOT / "apps/docs/src/content/docs/start/first-plugin.md"


def test_reference_walkthrough_uses_verbatim_executable_project_sources() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    blocks = re.findall(
        r"<!-- source: (examples/simple/[^ ]+) -->\n```(?:python|ts)\n(.*?)\n```",
        guide,
        re.DOTALL,
    )
    assert {path for path, _ in blocks} == {
        "examples/simple/simple/plugin.py",
        "examples/simple/tests/test_workflow_pure.py",
        "examples/simple/simple/surfaces.py",
        "examples/simple/web/src/app.ts",
    }
    for path, snippet in blocks:
        source = (ROOT / path).read_text(encoding="utf-8")
        # Snippets may omit enclosing test, class or callback indentation.
        assert textwrap.dedent(snippet).strip() in textwrap.dedent(source).strip() or (
            snippet.strip() in source
        ), path


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
