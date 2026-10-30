"""The generated ``serverClassFactory``, through the real adapter, without QGIS.

TASK-80 #1 asks for the three claims to be proven "registered through the
generated ``serverClassFactory`` against a scripted fake ``QgsServerInterface``
(pure tests, no QGIS)". The scaffold writes that factory into
``<plugin>/__init__.py`` and QGIS Server is what calls it in production, so the
test here starts from the generated project, installs the ``qgis.server``
stand-ins `qgis_server_support` keeps, and calls the very factory a user's
package exports. What it registers is then driven the way QGIS drives it: the
chain filter's ``onRequestReady``, the service's ``executeRequest`` and the
access-control object's ``layerPermissions``.

The difference from `test_server_adapter.py` is the entry point, not the
adapter: that file builds ``QgsServerHost`` itself, this one lets the generated
package build it, which is the step nothing covered before.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
import qgis_server_support as support
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

#: The scaffold's own starter hooks, at the priority ``@filter()`` defaults to.
DEFAULT_PRIORITY = 30


def scaffolded_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write ``qgis-sdk new --host server`` and make its package importable."""
    options = ScaffoldOptions.resolve("demo_server", host="server")
    root = tmp_path / "demo_server"
    write_scaffold(options, root)
    monkeypatch.syspath_prepend(str(root))
    return root


def import_entry(root: Path, package: str = "demo_server"):
    """Import the generated package the way QGIS Server's loader does.

    The generated package and its modules are dropped from ``sys.modules``
    first: two projects in one session write the same names, and a leftover
    ``<package>.plugin`` would hand one test the other test's hooks.
    """
    for name in [key for key in sys.modules if key.split(".")[0] == package]:
        del sys.modules[name]
    return importlib.import_module(package)


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The generated factory registered on a scripted interface, with one request."""
    support.install(monkeypatch)
    root = scaffolded_project(tmp_path, monkeypatch)
    entry = import_entry(root)
    handler = support.Handler(
        params={"SERVICE": "DEMOSERVER", "REQUEST": "GetCapabilities"}
    )
    interface = support.ServerInterface(handler=handler)
    host = entry.serverClassFactory(interface)
    return entry, host, interface, handler


def test_the_generated_factory_registers_three_objects(served) -> None:
    """One chain filter, one service and one access-control object, as QGIS wants."""
    _entry, host, interface, _handler = served

    assert host is not None
    assert list(interface.filters) == [DEFAULT_PRIORITY]
    assert len(interface.filters[DEFAULT_PRIORITY]) == 1
    assert [service.name() for service in interface.services] == ["DEMOSERVER"]
    assert [service.version() for service in interface.services] == ["1.0.0"]
    assert list(interface.access_controls) == [DEFAULT_PRIORITY]
    assert len(interface.access_controls[DEFAULT_PRIORITY]) == 1


def test_the_registered_filter_rewrites_the_request_qgis_will_serve(served) -> None:
    """Claim one: the filter sees the request and what it returns is what runs.

    The hook returns a new ``ServerRequest``; the adapter writes the difference
    back into the request handler, which is the object QGIS's own services read.
    """
    _entry, _host, interface, handler = served
    chain = interface.filters[DEFAULT_PRIORITY][0]

    assert chain.onRequestReady() is True

    assert handler.params["VERSION"] == "1.3.0"
    assert handler.params["SERVICE"] == "DEMOSERVER"


def test_the_registered_service_answers_the_request_it_owns(served) -> None:
    """Claim two: the service answers, through the response QGIS handed it."""
    _entry, _host, interface, handler = served
    interface.filters[DEFAULT_PRIORITY][0].onRequestReady()
    response = support.Response()

    interface.services[0].executeRequest(
        support.Request(params=handler.params), response, None
    )

    assert response.statusCode() == 200
    assert json.loads(response.body) == {
        "service": "DEMOSERVER",
        "version": "1.3.0",
    }


def test_an_access_hook_refusing_a_layer_through_the_same_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claim three: a refusal becomes QGIS's own ``LayerPermissions``.

    The starter ships a hook that allows everything, so the plugin is edited the
    way a user edits it - the entry, the factory and the registration are the
    generated ones.
    """
    support.install(monkeypatch)
    root = scaffolded_project(tmp_path, monkeypatch)
    plugin = root / "demo_server" / "plugin.py"
    plugin.write_text(
        plugin.read_text(encoding="utf-8").replace(
            "    return True", '    return layer != "secret"'
        ),
        encoding="utf-8",
    )
    entry = import_entry(root)
    interface = support.ServerInterface(handler=support.Handler())
    entry.serverClassFactory(interface)
    access = interface.access_controls[DEFAULT_PRIORITY][0]

    refused = access.layerPermissions(support.Layer("secret"))
    allowed = access.layerPermissions(support.Layer("parcels"))

    assert (refused.canRead, refused.canUpdate, refused.canDelete) == (
        False,
        False,
        False,
    )
    assert allowed.canRead is True


def test_the_registration_answers_capabilities_without_a_cache(
    served,
) -> None:
    """A per-request layer decision must not be served from a cached document."""
    _entry, _host, interface, _handler = served

    assert interface.access_controls[DEFAULT_PRIORITY][0].cacheKey() != ""
