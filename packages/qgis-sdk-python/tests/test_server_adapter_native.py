"""What the server adapter does on a QGIS that has no server bindings.

`qgis_sdk.adapters.qgis.server` has to be importable everywhere the other QGIS
adapters are - a plugin that declares `hosts = ["desktop", "server"]` imports one
module - and it must refuse to build a host, by name, only when someone actually
asks for one. This module runs in the Pixi environment, where the QGIS is real
and `qgis.server` is not there (conda-forge builds it out), which is the only
place that distinction can be checked.

The half that needs the bindings is `tests/test_server_native.py`, which runs on
the `QGIS 3.44 LTS` row.
"""

from __future__ import annotations

import pytest

# One layer per module: `qgis` is QGIS without the server bindings.
pytestmark = pytest.mark.qgis

try:
    from qgis import server as qgis_server_module
    from qgis.core import Qgis
    from qgis_sdk.adapters.qgis import server as adapter
    from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
    from qgis_sdk.server import ServerHooks
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the qgis layer needs QGIS: {error}", allow_module_level=True)


def test_importing_the_adapter_does_not_need_the_server_bindings() -> None:
    # The module is imported at the top of this file on a build that has no
    # `qgis.server` at all; reaching this line is the assertion.
    assert adapter.QgsServerHost is not None


def test_a_build_without_server_bindings_names_the_build_to_install() -> None:
    if hasattr(qgis_server_module, "QgsServer"):
        pytest.skip("this QGIS has server bindings; the refusal is the LTS row's job")

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as excinfo:
        adapter.qgis_server()

    message = str(excinfo.value)
    # The environment is the problem, so the message has to say how to fix it -
    # and name the one distribution that will never work.
    assert "qgis-server" in message
    assert "WITH_SERVER=ON" in message
    assert "conda-forge" in message
    assert Qgis.__name__ == "qgis.core"


def test_building_a_host_without_bindings_fails_before_registering_anything() -> None:
    if hasattr(qgis_server_module, "QgsServer"):
        pytest.skip("this QGIS has server bindings; the refusal is the LTS row's job")

    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        adapter.QgsServerHost(ServerHooks(()), object())
