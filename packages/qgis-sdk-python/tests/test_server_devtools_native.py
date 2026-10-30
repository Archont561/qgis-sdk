"""``qgis-sdk dev --host server`` against a real QGIS Server (TASK-80 AC 4).

Opt-in, because it starts a QGIS Server in this process::

    QGIS_SDK_SERVER_DEV=1 pytest tests/test_server_devtools_native.py

It runs on the ``QGIS 3.44 LTS`` row, which installs ``qgis-server`` and
``python3-qgis`` from a repository that builds ``WITH_SERVER=ON``; everywhere else
the module skips (no ``qgis.server``) - a skipped row is recorded as blocked by
the gate, never as passed (decision-52).

What it proves, through the command a user types: ``qgis-sdk dev --host server``
starts a real ``QgsServer`` on loopback, answers an HTTP request with the hook
the plugin declares, and **a saved edit to a filter is what the next request
runs** - the reload the AC asks for, not a restart. The edit changes the value a
``@server.filter`` stamps onto the request, and the service echoes it, so the
body proves both halves moved together.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import layers
import pytest

pytestmark = pytest.mark.server

pytest.importorskip(
    "qgis.server", reason="this QGIS was built without WITH_SERVER (no qgis.server)"
)

if not os.environ.get("QGIS_SDK_SERVER_DEV"):
    pytest.skip(
        "set QGIS_SDK_SERVER_DEV=1 to run `qgis-sdk dev --host server` against "
        "a real QGIS Server",
        allow_module_level=True,
    )

DEADLINE = 90.0

PYPROJECT = """[project]
name = "devtools-demo"
version = "0.1.0"
description = "A server plugin for the dev loop."
authors = [{ name = "Jane", email = "jane@example.org" }]
dependencies = ["qgis-sdk-runtime>=0.1,<99"]

[tool.qgis-sdk]
plugin = "devtools_demo.plugin:app"
qgis-minimum-version = "3.40"
hosts = ["server"]
"""

PLUGIN = '''"""One filter and one service: enough to see a reload in an HTTP body."""

from __future__ import annotations

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.server import (
    ServerContext,
    ServerRequest,
    ServerResponse,
    filter,
    service,
)

app = QgisSdkPlugin(id="devtools_demo", title="Devtools demo")

#: What the filter stamps on a request that carries no marker. `qgis-sdk dev`
#: must pick up a new value here on the next request, without a restart.
MARKER = "{marker}"


@filter(priority=10)
def stamp(
    ctx: ServerContext, request: ServerRequest, response: ServerResponse
) -> ServerRequest | None:
    if request.param("MARKER") is not None:
        return None
    return request.with_params(MARKER=MARKER)


@service(name="SDKDEMO", version="1.0.0")
def answer(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
    return ServerResponse.text(f"marker={{request.param('MARKER')}}")
'''

ENTRY = '''"""The entry QGIS Server calls, and the ``HOOKS`` a reload reads."""

from __future__ import annotations

from qgis_sdk.server import ServerHooks

from .plugin import answer, stamp

HOOKS = ServerHooks((stamp, answer))


def serverClassFactory(serverIface):
    from qgis_sdk.adapters.qgis.server import QgsServerHost

    return QgsServerHost(HOOKS, serverIface).register()
'''


def write_project(root: Path, marker: str) -> Path:
    """The project ``qgis-sdk dev`` will run; ``marker`` is what the filter stamps."""
    package = root / "devtools_demo"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(ENTRY, encoding="utf-8")
    (package / "plugin.py").write_text(PLUGIN.format(marker=marker), encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    return root


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def get(port: int, query: str) -> str:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/?{query}", timeout=10
    ) as response:
        return response.read().decode("utf-8", errors="replace")


def wait_for(port: int, expected: str, process: subprocess.Popen[str]) -> str:
    """Poll the server until the body says ``expected``; fail with what it did say."""
    deadline = time.monotonic() + DEADLINE
    seen: list[str] = []
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            body = get(port, "SERVICE=SDKDEMO")
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.25)
            continue
        seen.append(body)
        if expected in body:
            return body
        time.sleep(0.25)
    output = ""
    if process.poll() is not None:
        output = process.communicate(timeout=30)[0] or ""
    raise AssertionError(
        f"the server never answered {expected!r}; bodies seen: {seen[-5:]}; "
        f"qgis-sdk dev said:\n{output[-4000:]}"
    )


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_project(
        tmp_path_factory.mktemp("server-dev") / "devtools-demo", "first"
    )


@pytest.fixture
def running(project: Path) -> Iterator[tuple[subprocess.Popen[str], int]]:
    """``qgis-sdk dev --host server`` as a user runs it, in its own process."""
    port = free_port()
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")
    }
    env["PYTHONPATH"] = layers.source_path()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "qgis_sdk_tools",
            "dev",
            "--host",
            "server",
            "--port",
            str(port),
        ],
        cwd=project,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        yield process, port
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=60)


def test_the_server_answers_the_service_the_plugin_declares(
    project: Path, running: tuple[subprocess.Popen[str], int]
) -> None:
    process, port = running

    body = wait_for(port, "marker=first", process)

    assert body == "marker=first"


def test_a_saved_filter_edit_is_what_the_next_request_runs(
    project: Path, running: tuple[subprocess.Popen[str], int]
) -> None:
    """The AC's claim: the reload, not a restart, is what picks up the edit."""
    process, port = running
    wait_for(port, "marker=first", process)

    plugin = project / "devtools_demo" / "plugin.py"
    plugin.write_text(
        plugin.read_text(encoding="utf-8").replace(
            'MARKER = "first"', 'MARKER = "second"'
        ),
        encoding="utf-8",
    )

    body = wait_for(port, "marker=second", process)

    assert body == "marker=second"
    # The command stayed up: a reload that had failed would have ended it, and a
    # disabled plugin would answer 503 instead of the service's body.
    assert process.poll() is None
