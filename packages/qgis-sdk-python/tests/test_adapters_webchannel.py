"""The WebChannel adapter imports Qt only when it is asked for one.

The interesting property here is the optional-dependency rule the SDK applies to
every Qt adapter: a runtime without PyQt6 gets an actionable error, not an
ImportError at module import. When the bindings are present - which is the case
in the CI job that installs QGIS - the same call has to produce a QObject.
"""

from __future__ import annotations

from qgis_sdk.adapters.webchannel import (
    WEBCHANNEL_DEPENDENCY,
    create_channel_object,
    webchannel_available,
)
from qgis_sdk.bridge import BridgeOperation, Dispatcher
from qgis_sdk.models.errors import QgisSdkOptionalDependencyError

ECHO = BridgeOperation(id="demo.echo", title="Echo the payload")


def _dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register(ECHO, lambda payload: {"echo": payload})
    return dispatcher


def test_the_adapter_reports_availability_instead_of_importing_qt() -> None:
    assert isinstance(webchannel_available(), bool)


def test_a_runtime_without_the_bindings_gets_an_actionable_error() -> None:
    dispatcher = _dispatcher()
    binding = dispatcher.bind(view_id="view-1", origin="qgis://desktop")

    if webchannel_available():
        channel = create_channel_object(dispatcher, binding)
        assert channel is not None
        return

    try:
        create_channel_object(dispatcher, binding)
    except QgisSdkOptionalDependencyError as error:
        assert error.dependency == WEBCHANNEL_DEPENDENCY
        assert "WebChannel" in error.installation_hint
    else:  # pragma: no cover - defensive: the probe and the factory disagree
        raise AssertionError("a missing binding must be reported, not ignored")
