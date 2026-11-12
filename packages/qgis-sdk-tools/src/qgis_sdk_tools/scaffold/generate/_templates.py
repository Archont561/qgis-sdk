from __future__ import annotations

from dataclasses import dataclass

APP_MAIN_MODULE = '''"""`python -m {plugin}`: the entry of the standalone app.

There is no QGIS to load a ``classFactory`` into, so this module *is* the entry
(decision-52 point 3): ``qgis-sdk run`` starts it, and a distribution built with
``qgis-sdk build --target app`` installs it as a console script. The flags are
``qgis_sdk.app``'s - ``--headless``, ``--once``, ``--grace``, ``--title`` and
``--`` before anything meant for Qt - so nothing here parses argv itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from qgis_sdk.app import main as run_app

from .plugin import app


def main(argv: Sequence[str] | None = None) -> int:
    """Run {title}; close the window or press Ctrl+C to leave."""
    return run_app(app, argv)


if __name__ == "__main__":
    raise SystemExit(main())
'''
APP_STARTER_TEST = '''"""Smoke tests for {title}: the app host, without QGIS and without a display.

``qgis_sdk.app.run`` is driven by ``FakeAppBackend``: the real session starts the
application, starts the plugin, delivers what is queued and stops - so these
tests fail when the declarations stop agreeing with the host, not only when QGIS
is missing.
"""

from qgis_sdk import describe
from qgis_sdk.app import run
from qgis_sdk.core import Host
from qgis_sdk.testing import FakeAppBackend

from {plugin}.plugin import app


def test_the_app_starts_headless_and_stops_in_order() -> None:
    backend = FakeAppBackend()

    assert run(app, backend=backend, once=True) == 0
    assert backend.calls == ["init", "build", "process_events", "exit"]
    assert backend.surface.context.host is Host.APP


def test_declared_actions_are_the_plugins_public_surface() -> None:
    description = describe(app)

    assert [action.id for action in description.actions] == [{action_ids}]
'''
SERVER_ENTRY_POINT = '''"""``serverClassFactory``: the entry QGIS Server calls for {title}.

QGIS Server does not load ``classFactory``. It imports this module and calls
``serverClassFactory(serverIface)``, which is what ``metadata.txt``'s
``server=True`` tells it to do. The hooks themselves stay in ``plugin.py``;
this file is the only one that imports the server adapter.
"""

from __future__ import annotations

from qgis_sdk.server import ServerHooks

from .plugin import answer, default_version, everything_public

HOOKS = ServerHooks((default_version, answer, everything_public))


def serverClassFactory(serverIface):
    """Register every hook with QGIS Server; it keeps what this returns."""
    from qgis_sdk.adapters.qgis.server import QgsServerHost

    return QgsServerHost(HOOKS, serverIface).register()
'''
SERVER_PLUGIN_MODULE = '''"""{title}: a minimal qgis-sdk plugin for QGIS Server."""

from __future__ import annotations

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.server import (
    ServerContext,
    ServerRequest,
    ServerResponse,
    access_control,
    filter,
    service,
)

# The declaration `build`, `dev` and `describe` read: id, title, and whatever
# the plugin adds to them. A server plugin declares hooks instead of actions.
app = QgisSdkPlugin(id="{plugin}", title="{title}")


@filter()
def default_version(
    ctx: ServerContext, request: ServerRequest, response: ServerResponse
):
    """Give a request that names no VERSION the one this plugin documents.

    ``None`` passes the request on, a ``ServerRequest`` rewrites what the hooks
    after this one see, and a ``ServerResponse`` answers and stops the chain.
    """
    if request.param("VERSION") is None:
        return request.with_params(VERSION="1.3.0")
    return None


@service(name="{service_name}", version="1.0.0")
def answer(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
    """Answer the OGC service this plugin owns - here, a JSON echo."""
    return ServerResponse.json(
        {{"service": "{service_name}", "version": request.param("VERSION")}}
    )


@access_control()
def everything_public(ctx: ServerContext, request: ServerRequest, layer: str) -> bool:
    """Allow every layer; returning ``False`` is a 403 naming the layer."""
    return True
'''
SERVER_STARTER_TEST = '''"""Smoke tests for {title}: the hooks through the scripted server.

No QGIS and no display. ``FakeServerInterface`` is the interface ``qgis.server``
provides - it records what a host registers - and ``serve`` drives the same
dispatcher a deployed server drives, so these tests fail when the hooks stop
agreeing with each other, not only when QGIS is missing.
"""

import json

from qgis_sdk.core import ResourceScope
from qgis_sdk.server import ServerContext, ServerHost, ServerRequest, ServerResponse
from qgis_sdk.testing import FakeServerInterface

from {plugin} import HOOKS


def request(**params: str) -> ServerRequest:
    return ServerRequest(
        method="GET",
        url="http://localhost/qgis/qgis_mapserv.fcgi",
        params=params,
    )


def test_a_request_without_a_version_is_rewritten_and_answered() -> None:
    answered = FakeServerInterface().serve(
        HOOKS, request(SERVICE="{service_name}")
    )

    assert answered.status == 200
    assert json.loads(answered.body) == {{
        "service": "{service_name}",
        "version": "1.3.0",
    }}


def test_the_access_hook_allows_a_layer_and_the_host_builds_the_refusal() -> None:
    scope = ResourceScope()
    host = ServerHost(HOOKS, FakeServerInterface())
    served = request(SERVICE="{service_name}")
    try:
        context = ServerContext(scope, served, ServerResponse())
        assert host.permits(context, served, "parcels") is True
    finally:
        scope.close()
'''
SERVER_README = """# {title}

A minimal [qgis-sdk](https://pypi.org/project/qgis-sdk/) plugin for **QGIS
Server**, generated by `qgis-sdk new --host server`. `{plugin}/plugin.py` holds
the hooks and the declaration; `{plugin}/__init__.py` is the entry QGIS Server
calls.

## What runs where

QGIS Server does not load `classFactory`. It imports `{plugin}` and calls
`serverClassFactory(serverIface)`, which turns the hooks into the objects the
server drives:

| SDK declaration | the object QGIS calls | when |
| --- | --- | --- |
| every `@filter` | one `QgsServerFilter` | `onRequestReady`, at the lowest priority the plugin declares |
| each `@service` | one `QgsService` | `executeRequest`, when the request names that `SERVICE` and version |
| every `@access_control` | one `QgsAccessControlFilter` | `layerPermissions`, per layer, while a service renders |

`[tool.qgis-sdk] hosts` says `server`, so `qgis-sdk check` reports a Desktop-only
declaration (`@toolbar`, a `Dialog`, a web page) as HOST001 instead of shipping a
hook that can never be called. A `ServerContext` never carries `ui`, `desktop`,
`views` or `workers`, and its `ctx.jobs` is request-scoped: a job a hook submits
is abandoned when the response is sent (decision-52). Work that must outlive the
request says so with `ctx.jobs.plugin`.

The QGIS this runs in has to be built with `WITH_SERVER=ON` **and** its Python
bindings: the Debian/Ubuntu `qgis-server` plus `python3-qgis` packages, the
official installers, or a source build with `-DWITH_SERVER=ON
-DWITH_BINDINGS=ON`. conda-forge passes `-D WITH_SERVER=FALSE`, so no conda QGIS
has `qgis.server`, and `qgis-sdk check` reports that as HOST003 there.

## Build and install

```sh
qgis-sdk build
```

writes `dist/{plugin}-<version>.zip` with `metadata.txt` (`server=True`), the
`serverClassFactory` entry and the SDK runtime inside. Unpack it where QGIS
Server looks for plugins (`QGIS_PLUGINPATH`, or the plugin directory of the
deployment) and restart the server.

## Tests

```sh
qgis-sdk test      # pure: the hooks through qgis_sdk.testing.FakeServerInterface
pytest -q          # the same suite, your way
```

The starter tests need no QGIS: the scripted interface serves a request through
the same dispatcher a deployed server drives. Run them inside a server-capable
QGIS to cover the bindings half as well.
"""
PYPROJECT = """# Generated by `qgis-sdk new`. The project is the plugin: `qgis-sdk dev` runs
# this directory inside QGIS and `qgis-sdk build` turns it into the ZIP. QGIS's
# metadata.txt and classFactory are derived from this file (decision-43).
[project]
name = "{name}"
version = "{version}"
description = "{description}"
authors = [{{ name = "{author}", email = "{email}" }}]
requires-python = ">=3.11"
# The runtime the plugin is written for; `build` vendors the installed one and
# `check` reports a mismatch (VERSION004). `qgis-sdk` itself never installs.
dependencies = ["{runtime_requirement}"]

[dependency-groups]
dev = ["{tools_requirement}"]

[tool.qgis-sdk]
# The application QGIS runs; `build` and `dev` bind classFactory to it through
# qgis_sdk.adapters.desktop.host().
plugin = "{plugin}.plugin:app"
# The hosts this project runs on (decision-52): `desktop` is loaded by QGIS
# through classFactory, `server` by QGIS Server through serverClassFactory.
hosts = ["{host}"]
qgis-minimum-version = "{qgis_minimum_version}"
experimental = true
# Where QGIS is, when `qgis-sdk test` and `qgis-sdk dev` should not discover it
# (they otherwise try QGIS_PREFIX_PATH, `qgis` on PATH, then this environment).
# qgis-prefix = "/path/to/qgis"

# Extra metadata.txt keys, passed through as written:
# [tool.qgis-sdk.metadata]
# homepage = "https://example.org/{name}"
# tags = "vector"
{web_table}
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
# The SDK's pytest plugin: the `qgis` and `desktop` markers, the `qgis_app` and
# `qgis_iface` fixtures, and the guard `qgis-sdk test` relies on. Plain `pytest`
# keeps working; `qgis-sdk test --target qgis|desktop` runs the native layers.
addopts = "-p qgis_sdk_tools.pytest_plugin"
"""
WEB_TABLE = """
[tool.qgis-sdk.web]
# The page in web/: shown as a {placement}; `grants` lists the host grants
# (`layers.read`) or operation ids (`project.layer_ids`) the page may use;
# `qgis-sdk bridge generate --host` renders the catalogue. The starter page's
# layer picker reads `layers.list`, which `layers.read` covers, and
# `algorithms.run` lets `runAlgorithm` from web/src/processing.schema.ts run
# the host's Processing algorithms.
placement = "{placement}"
grants = ["layers.read", "algorithms.run"]
"""
GITIGNORE = """__pycache__/
.pytest_cache/
# `qgis-sdk dev` keeps its isolated QGIS profile and the generated host package here.
.qgis-sdk/
# `qgis-sdk build` writes the installable ZIP here.
dist/
"""


@dataclass(frozen=True, slots=True)
class GeneratedFile:
    """One file of the plan: a project-relative path and its exact content."""

    path: str
    content: str
