"""Stand-ins for the ``qgis.server`` objects the server adapter talks to.

Two test modules need the same cast: `test_server_wire.py` checks the mapping
between the plain models and the QGIS objects, and `test_server_adapter.py`
checks that a plugin's hooks land in the three objects QGIS calls. Both run on a
machine with no QGIS, so both need objects that behave like the C++ ones and do
nothing else.

The stand-ins follow QGIS's own spellings - ``parameterMap``, ``appendBody``,
``setResponseHeader``, ``layerPermissions``, ``LayerPermissions`` - because the
point is to catch an adapter that calls the wrong one. They are not a simulation:
where the real class does something clever, the stand-in returns a fixed answer.
That is why `tests/test_server_native.py` drives the same adapter through a real
``QgsServer`` on the `QGIS 3.44 LTS` row: if a test passes here and fails there,
the difference is QGIS, not this file.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest


class Url:
    """``QUrl``: the adapter only calls ``toString``."""

    def __init__(self, value: str = "http://localhost/qgis/qgis_mapserv.fcgi") -> None:
        self._value = value

    def toString(self) -> str:
        return self._value


class Parameters:
    """``QgsServerParameters``: the adapter only calls ``toMap``."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = dict(values)

    def toMap(self) -> dict[str, str]:
        return dict(self._values)


class Request:
    """``QgsServerRequest``, as a service is handed it."""

    GET = 2
    POST = 3

    def __init__(
        self,
        params: dict[str, str] | None = None,
        *,
        method: int = GET,
        url: str = "http://localhost/qgis/qgis_mapserv.fcgi",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self._params = dict(params or {})
        self._method = method
        self._url = url
        self._headers = dict(headers or {})
        self._body = body

    @staticmethod
    def methodToString(method: int) -> str:
        return {Request.GET: "GET", Request.POST: "POST"}[method]

    def method(self) -> int:
        return self._method

    def url(self) -> Url:
        return Url(self._url)

    def serverParameters(self) -> Parameters:
        return Parameters(self._params)

    def headers(self) -> dict[str, str]:
        return dict(self._headers)

    def data(self) -> bytes:
        return self._body


class Response:
    """``QgsServerResponse``: what a service writes its answer into."""

    def __init__(self) -> None:
        self.status = 200
        self._headers: dict[str, str] = {}
        self.body = b""
        self.cleared = 0

    def statusCode(self) -> int:
        return self.status

    def setStatusCode(self, code: int) -> None:
        self.status = code

    def setHeader(self, name: str, value: str) -> None:
        self._headers[name] = value

    def headers(self) -> dict[str, str]:
        return dict(self._headers)

    def write(self, body: bytes) -> int:
        self.body += body
        return len(body)

    def data(self) -> bytes:
        return self.body

    def clear(self) -> None:
        self.cleared += 1
        self._headers = {}
        self.body = b""
        self.status = 200


class Handler:
    """``QgsRequestHandler``: the filter path's only handle on the request."""

    def __init__(
        self,
        params: dict[str, str] | None = None,
        *,
        url: str = "http://localhost/qgis/qgis_mapserv.fcgi",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.params = dict(params or {})
        self.request_headers = dict(headers or {})
        self._url = url
        self.status = 200
        self.response_headers: dict[str, str] = {}
        self.body = b""
        self.exception: object | None = None
        self.cleared = 0

    def url(self) -> str:
        return self._url

    def parameterMap(self) -> dict[str, str]:
        return dict(self.params)

    def requestHeaders(self) -> dict[str, str]:
        return dict(self.request_headers)

    def setParameter(self, name: str, value: str) -> None:
        self.params[name] = value

    def removeParameter(self, name: str) -> None:
        self.params.pop(name, None)

    def setStatusCode(self, code: int) -> None:
        self.status = code

    def setResponseHeader(self, name: str, value: str) -> None:
        self.response_headers[name] = value

    def appendBody(self, body: bytes) -> None:
        self.body += body

    def setServiceException(self, exception: Any) -> None:
        self.exception = exception

    def clear(self) -> None:
        self.cleared += 1
        self.response_headers = {}
        self.body = b""
        self.status = 200


class ServerException(Exception):
    """``QgsMapServiceException``, the switch that stops QGIS's own dispatch."""


class LayerPermissions:
    """``QgsAccessControlFilter.LayerPermissions``: four flags, all allowed."""

    def __init__(self) -> None:
        self.canRead = True
        self.canInsert = True
        self.canUpdate = True
        self.canDelete = True


class Layer:
    """``QgsMapLayer``: QGIS asks its permission question with this."""

    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


# -- the classes a plugin subclasses -------------------------------------------------


class ServerFilter:
    def __init__(self, server_interface: Any) -> None:
        self._interface = server_interface

    def serverInterface(self) -> Any:
        return self._interface

    def onRequestReady(self) -> bool:
        return True

    def onResponseComplete(self) -> bool:
        return True


class Service:
    def name(self) -> str:
        return ""

    def version(self) -> str:
        return ""

    def executeRequest(self, request: Any, response: Any, project: Any = None) -> None:
        return None


class AccessControlFilter:
    def __init__(self, server_interface: Any) -> None:
        self._interface = server_interface

    def serverInterface(self) -> Any:
        return self._interface

    def layerPermissions(self, layer: Any) -> LayerPermissions:
        return LayerPermissions()


class ServerInterface:
    """``QgsServerInterface``: where registered objects land and where they ask."""

    def __init__(self, handler: Handler | None = None) -> None:
        self.filters: dict[int, list[Any]] = {}
        self.access_controls: dict[int, list[Any]] = {}
        self.services: list[Any] = []
        self.handler = handler

    def registerFilter(self, item: Any, priority: int = 0) -> None:
        self.filters.setdefault(priority, []).append(item)

    def registerAccessControl(self, item: Any, priority: int = 0) -> None:
        self.access_controls.setdefault(priority, []).append(item)

    def registerService(self, item: Any) -> None:
        self.services.append(item)

    def serviceRegistry(self) -> ServerInterface:
        return self

    def requestHandler(self) -> Handler | None:
        return self.handler


def module() -> types.ModuleType:
    """A stand-in for ``qgis.server`` holding the names the adapter reaches for."""
    module = types.ModuleType("qgis.server")
    module.QgsServerFilter = ServerFilter
    module.QgsService = Service
    module.QgsAccessControlFilter = type(
        "QgsAccessControlFilter",
        (AccessControlFilter,),
        {"LayerPermissions": LayerPermissions},
    )
    module.QgsMapServiceException = ServerException
    return module


def install(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Make ``from qgis import server`` resolve to the stand-in."""
    fake = module()
    package = types.ModuleType("qgis")
    package.server = fake
    monkeypatch.setitem(sys.modules, "qgis", package)
    monkeypatch.setitem(sys.modules, "qgis.server", fake)
    return fake
