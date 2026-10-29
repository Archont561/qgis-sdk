"""The optional MCP command must not import its dependency unless invoked."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner


def test_mcp_command_without_optional_dependency_explains_installation(
    tmp_path: Path, monkeypatch
):
    import builtins

    original = builtins.__import__

    def without_mcp(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_mcp)
    runtime = FakeCliRuntime(cwd=tmp_path)
    result = CliRunner().invoke(app, ["mcp", "--project", str(tmp_path)], obj=runtime)
    assert result.exit_code == 2
    assert "qgis-sdk[mcp]" in runtime.stderr


def test_regular_cli_import_does_not_eagerly_import_mcp(tmp_path: Path):
    script = """import sys\nimport qgis_sdk_tools.__main__\nassert not any(k == 'mcp' or k.startswith('mcp.') for k in sys.modules)\n"""
    import os

    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_stdio_server_exposes_and_runs_cli_commands(tmp_path: Path):
    import os

    import pytest

    pytest.importorskip("mcp")
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from qgis_sdk import __file__ as runtime_file
    from qgis_sdk_tools import __file__ as tools_file

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(tools_file).parent.parent), str(Path(runtime_file).parent.parent)]
    )

    async def exercise():
        executable = Path(sys.executable).parent / (
            "qgis-sdk.exe" if os.name == "nt" else "qgis-sdk"
        )
        command = str(executable) if executable.is_file() else sys.executable
        prefix = [] if executable.is_file() else ["-m", "qgis_sdk_tools"]
        params = StdioServerParameters(
            command=command,
            args=[*prefix, "mcp", "--project", str(tmp_path)],
            env=env,
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            tools = {tool.name for tool in (await client.list_tools()).tools}
            commands = {
                "qgis_sdk_new",
                "qgis_sdk_scaffold",
                "qgis_sdk_bridge_generate",
                "qgis_sdk_processing_generate",
                "qgis_sdk_check",
                "qgis_sdk_build",
                "qgis_sdk_test",
                "qgis_sdk_dev",
                "qgis_sdk_targets",
            }
            # The tool inventory stays aligned when the CLI adds a command.
            import typer

            cli = typer.main.get_command(app)
            cli_commands = set()
            for name, item in cli.commands.items():
                # Plugin REST access is intentionally not adapted to MCP.
                if name in {"mcp", "plugin"}:
                    continue
                if hasattr(item, "commands"):
                    cli_commands.update(
                        f"qgis_sdk_{name}_{child}" for child in item.commands
                    )
                else:
                    cli_commands.add(f"qgis_sdk_{name}")
            assert commands == cli_commands
            assert commands <= tools
            for command in commands - {"qgis_sdk_dev"}:
                result = await client.call_tool(command, {"args": ["--help"]})
                assert not result.is_error, (command, result)
                assert result.structured_content["exit_code"] == 0
            result = await client.call_tool(
                "qgis_sdk_new", {"args": ["demo", "--no-input"]}
            )
            assert not result.is_error
            assert result.structured_content["exit_code"] == 0
            assert (tmp_path / "demo" / "pyproject.toml").is_file()
            result = await client.call_tool("qgis_sdk_check", {"args": ["missing"]})
            assert result.structured_content["exit_code"] != 0
            result = await client.call_tool("qgis_sdk_targets", {"args": ["--json"]})
            assert result.structured_content["exit_code"] == 0
            assert '"targets"' in result.structured_content["stdout"]
            started = await client.call_tool("qgis_sdk_dev", {"args": ["--help"]})
            assert not started.is_error
            session_id = started.structured_content["session_id"]
            with anyio.fail_after(10):
                while True:
                    status = await client.call_tool(
                        "qgis_sdk_dev_status", {"session_id": session_id}
                    )
                    if not status.structured_content["running"]:
                        break
                    await anyio.sleep(0.05)
            assert status.structured_content["exit_code"] == 0
            # Help rendering varies with terminal width; the session lifecycle
            # below is what this test verifies, so only require captured output.
            assert status.structured_content["stdout"]
            stopped = await client.call_tool(
                "qgis_sdk_dev_stop", {"session_id": session_id}
            )
            assert not stopped.is_error
            missing = await client.call_tool(
                "qgis_sdk_dev_status", {"session_id": session_id}
            )
            assert missing.is_error

    anyio.run(exercise)


def test_package_extras_are_optional_and_the_kit_forwards_to_tools():
    import tomllib

    root = Path(__file__).resolve().parents[3]
    tools = tomllib.loads((root / "packages/qgis-sdk-tools/pyproject.toml").read_text())
    kit = tomllib.loads((root / "packages/qgis-sdk-python/pyproject.toml").read_text())
    tools_project = tools["project"]
    kit_project = kit["project"]
    version = tools_project["version"]
    assert tools_project["optional-dependencies"]["mcp"] == ["mcp==2.3.0"]
    assert kit_project["optional-dependencies"]["mcp"] == [
        f"qgis-sdk-tools[mcp]=={version}"
    ]
    assert all(
        not dependency.startswith("mcp") for dependency in tools_project["dependencies"]
    )
    assert all("[mcp]" not in dependency for dependency in kit_project["dependencies"])


def test_captured_output_keeps_the_tail_of_a_long_stream():
    """The diagnostic end of an oversized stream must survive the cap."""
    import asyncio

    import pytest

    pytest.importorskip("mcp")
    from qgis_sdk_tools import mcp

    async def capture():
        stream = asyncio.StreamReader()
        stream.feed_data(b"noise\n" + b"x" * (mcp._LIMIT + 1024) + b"\nTRACEBACK\n")
        stream.feed_eof()
        output = bytearray()
        truncated = [False]
        await mcp._capture(stream, output, truncated)
        return bytes(output), truncated[0]

    output, truncated = asyncio.run(capture())
    assert truncated is True
    assert output.endswith(b"\nTRACEBACK\n"), "the tail is what diagnoses a failure"
    assert len(output) == mcp._LIMIT
    assert b"noise" not in output
