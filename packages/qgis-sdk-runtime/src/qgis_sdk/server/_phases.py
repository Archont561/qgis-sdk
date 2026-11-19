"""The phases one request is served in, and the record they share.

``ServerHost.serve`` is written as three phases so no one function holds the
whole dispatch; the record is what travels between them (decision-81).
"""

from __future__ import annotations

from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

from ._request import ServerRequest
from ._response import ServerResponse

__all__ = [
    "EarlyAnswer",
    "ServeState",
    "serve_filters",
    "serve_service",
    "serve_unserved",
]


class ServeState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class EarlyAnswer:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def serve_filters(_s):
    _s.rewritten = _s.self.rewrite(_s.context, _s.request, _s.response)
    if isinstance(_s.rewritten, ServerResponse):
        return EarlyAnswer(_s.rewritten)
    _s.denied = _s.self.denied_layer(_s.context, _s.rewritten)
    if _s.denied is not None:
        return EarlyAnswer(_s.denied)
    _s.service = _s.self.service_for(_s.rewritten)


def serve_service(_s):
    if _s.service is not None:
        _s.answer = _s.service(_s.context, _s.rewritten)
        if not isinstance(_s.answer, ServerResponse):
            raise QgisSdkUnsupportedCapabilityError(
                f"@server.service `{_s.service.__name__}` returned "
                f"{type(_s.answer).__name__}; a service answers with a "
                "ServerResponse"
            )
        return EarlyAnswer(_s.answer)


def serve_unserved(_s):
    return EarlyAnswer(
        _s.response.write_text(
            f"SERVICE {_s.rewritten.param('SERVICE') or '(missing)'!r} is not served "
            "by this plugin",
            status=400,
        )
    )


def requested_layers(request: ServerRequest) -> tuple[str, ...]:
    """The layers a request names, in the order it names them."""
    requested = request.param("LAYERS") or request.param("LAYER") or ""
    return tuple(name.strip() for name in requested.split(",") if name.strip())
