"""The QGIS Server mapping, proven without QGIS.

`qgis_sdk.adapters._server` is where an SDK hook's plain request and response
meet `QgsServerRequest`, `QgsServerResponse` and `QgsRequestHandler`. Nothing in
it imports Qt - the objects are passed in and asked for the same calls QGIS's own
`handleRequest` makes - so the whole mapping is testable here against stand-ins,
which is where a wrong parameter name or a swallowed rewrite is caught cheaply.

The end-to-end proof is elsewhere: `tests/test_server_native.py` registers these
objects on a real `QgsServerInterface` and drives a real request through them on
the `QGIS 3.44 LTS` CI row (TASK-80 AC 2). This module is the part that says
which call goes where.
"""

from __future__ import annotations

from typing import Any

import pytest
from qgis_sdk.adapters._server import (
    UNKNOWN_METHOD,
    request_from_handler,
    rewrite_parameters,
    sdk_request,
    sdk_response,
    stop_dispatch,
    write,
)
from qgis_sdk.server import ServerRequest, ServerResponse
from qgis_server_support import Handler, Request, Response, ServerException
from qgis_server_support import module as server_module

# -- reading what QGIS hands a service ---------------------------------------------


def test_a_service_request_arrives_as_the_plain_model() -> None:
    request = Request(
        {"SERVICE": "WMS", "REQUEST": "GetCapabilities"},
        method=Request.POST,
        headers={"Accept": "text/xml"},
        body=b"body",
    )

    model = sdk_request(request)

    assert model.method == "POST"
    assert model.url == "http://localhost/qgis/qgis_mapserv.fcgi"
    assert model.param("service") == "WMS"
    assert model.header("accept") == "text/xml"
    assert model.body == b"body"


def test_the_parameters_are_matched_the_way_ogc_matches_them() -> None:
    model = sdk_request(Request({"SERVICE": "WMS"}))

    assert model.param("SERVICE") == model.param("service") == "WMS"
    assert model.param("VERSION", "1.3.0") == "1.3.0"


def test_the_handler_path_reports_no_verb_rather_than_guessing_one() -> None:
    # `QgsServerFilter` gets no request object and `QgsRequestHandler` exposes the
    # URL, the headers and the merged parameters but not the method, so the model
    # says it does not know instead of claiming GET.
    model = request_from_handler(Handler({"SERVICE": "WMS"}, headers={"Accept": "x"}))

    assert model.method == UNKNOWN_METHOD == ""
    assert model.url == "http://localhost/qgis/qgis_mapserv.fcgi"
    assert model.param("SERVICE") == "WMS"
    assert model.header("Accept") == "x"


def test_a_qgis_response_is_read_back_as_the_plain_model() -> None:
    response = Response()
    response.status = 404
    response.setHeader("Content-Type", "text/plain")
    response.write(b"missing")

    model = sdk_response(response)

    assert model.status == 404
    assert model.header("content-type") == "text/plain"
    assert model.body == b"missing"


# -- writing what a hook answered ---------------------------------------------------


def test_the_writer_speaks_the_service_response_language() -> None:
    response = Response()

    write(response, ServerResponse(status=201, body=b"created"))

    assert response.status == 201
    assert response.headers()["Content-Type"] == "text/xml"
    assert response.body == b"created"


def test_the_writer_speaks_the_request_handler_language() -> None:
    handler = Handler()

    write(handler, ServerResponse(status=403, body=b"refused"))

    assert handler.status == 403
    assert handler.response_headers["Content-Type"] == "text/xml"
    assert handler.body == b"refused"


def test_an_empty_body_is_not_written() -> None:
    handler = Handler()

    write(handler, ServerResponse(status=204))

    assert handler.body == b""
    assert handler.status == 204


# -- carrying a rewrite into the request the services read --------------------------


def test_a_rewrite_sets_changes_and_additions_and_removes_drops() -> None:
    handler = Handler({"SERVICE": "WMS", "VERSION": "1.3.0", "LAYERS": "roads"})
    before = request_from_handler(handler)
    after: ServerRequest = ServerRequest(
        method=before.method,
        url=before.url,
        params={"SERVICE": "WMS", "VERSION": "1.1.1", "EXTRA": "yes"},
    )

    rewrite_parameters(handler, before, after)

    assert handler.params == {"SERVICE": "WMS", "VERSION": "1.1.1", "EXTRA": "yes"}


def test_a_rewrite_that_changes_nothing_touches_nothing() -> None:
    handler = Handler({"SERVICE": "WMS"})
    before = request_from_handler(handler)

    rewrite_parameters(handler, before, before)

    assert handler.params == {"SERVICE": "WMS"}


# -- stopping the dispatcher for a request a filter answered ------------------------


def test_a_filter_answer_stops_the_qgis_services() -> None:
    handler = Handler()

    assert stop_dispatch(server_module(), handler) is True
    assert isinstance(handler.exception, ServerException)


def test_a_build_without_the_exception_class_does_not_stop_dispatch() -> None:
    # Older or differently built bindings may not expose it; the answer is still
    # written, the caller just cannot promise the services were skipped.
    handler = Handler()

    assert stop_dispatch(object(), handler) is False
    assert handler.exception is None


def test_a_binding_that_refuses_the_exception_does_not_stop_dispatch() -> None:
    class Refusing(Handler):
        def setServiceException(self, exception: Any) -> None:
            raise TypeError("this binding wants a QgsServerException")

    assert stop_dispatch(server_module(), Refusing()) is False


def test_an_unexpected_state_is_not_a_silent_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The one thing this helper must never do is report a stop it did not cause:
    # the caller clears the response on the strength of that answer.
    handler = Handler()

    class Exploding(Handler):
        def setServiceException(self, exception: Any) -> None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        stop_dispatch(server_module(), Exploding())
    assert handler.exception is None
