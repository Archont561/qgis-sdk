"""The answer a server hook writes: a status, headers and a body, in plain Python.

A hook mutates the context's response with :meth:`ServerResponse.set_header` and
the ``write_*`` helpers, or returns a response of its own to answer the request
without the hooks after it running. The adapter is what turns this into whatever
``QgsServerResponse`` the host holds, so no hook ever touches a Qt object
(decision-52).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ._request import CaseInsensitiveMapping

__all__ = ["ServerResponse"]

_CONTENT_TYPES = {
    "json": "application/json; charset=utf-8",
    "text": "text/plain; charset=utf-8",
    "xml": "text/xml; charset=utf-8",
}


@dataclass(slots=True)
class ServerResponse:
    """The response being built for one request.

    ``status`` is the HTTP status, ``headers`` are matched without regard to
    case, and ``body`` is the bytes the host will write. A hook that returns the
    context's response changes it in place; a hook that returns a different one
    answers the request itself, which is the only way to short-circuit.

    Attributes:
        status: The HTTP status the host will send.
        headers: The headers, matched without regard to case.
        body: The bytes the host will write.
    """

    status: int = 200
    headers: CaseInsensitiveMapping = field(
        default_factory=lambda: CaseInsensitiveMapping({"Content-Type": "text/xml"})
    )
    body: bytes = b""

    def __post_init__(self) -> None:
        if not isinstance(self.headers, CaseInsensitiveMapping):
            self.headers = CaseInsensitiveMapping(self.headers)

    # -- reading -----------------------------------------------------------------

    def header(self, name: str, default: str | None = None) -> str | None:
        """Return the response header ``name`` whatever its case.

        Args:
            name: The header to read.
            default: What to return when it is not set.
        """
        return self.headers.get(name, default)

    @property
    def status_message(self) -> str:
        """The reason phrase for :attr:`status`, or ``"Unknown"``."""
        from http import HTTPStatus

        try:
            return HTTPStatus(self.status).phrase
        except ValueError:
            return "Unknown"

    # -- writing -----------------------------------------------------------------

    def set_header(self, name: str, value: str) -> ServerResponse:
        """Set one header, replacing an entry of any other case; returns ``self``.

        Args:
            name: The header to set.
            value: What it is set to.
        """
        headers = {key: self.headers[key] for key in self.headers}
        for existing in list(headers):
            if existing.casefold() == str(name).casefold():
                del headers[existing]
        headers[str(name)] = str(value)
        self.headers = CaseInsensitiveMapping(headers)
        return self

    def set_status(self, status: int) -> ServerResponse:
        """Set the HTTP status; returns ``self``.

        Args:
            status: The status, such as ``404``.
        """
        self.status = int(status)
        return self

    def write(self, body: bytes | str) -> ServerResponse:
        """Append to the body, encoding text as UTF-8; returns ``self``.

        Args:
            body: The bytes or text to append.
        """
        chunk = body.encode("utf-8") if isinstance(body, str) else bytes(body)
        self.body += chunk
        return self

    def write_text(self, content: str, *, status: int | None = None) -> ServerResponse:
        """Answer with text, setting the status when one is given.

        Args:
            content: The body, replacing whatever was written before.
            status: The status to answer with, or ``None`` to keep the current.
        """
        if status is not None:
            self.status = int(status)
        self.set_header("Content-Type", _CONTENT_TYPES["text"])
        self.body = content.encode("utf-8")
        return self

    def write_xml(self, content: str, *, status: int | None = None) -> ServerResponse:
        """Answer with XML, the default content type of a WMS/WFS response.

        Args:
            content: The body, replacing whatever was written before.
            status: The status to answer with, or ``None`` to keep the current.
        """
        if status is not None:
            self.status = int(status)
        self.set_header("Content-Type", _CONTENT_TYPES["xml"])
        self.body = content.encode("utf-8")
        return self

    def write_json(self, data: Any, *, status: int | None = None) -> ServerResponse:
        """Answer with JSON, encoded the way the rest of the SDK encodes it.

        Args:
            data: What to serialize.
            status: The status to answer with, or ``None`` to keep the current.
        """
        if status is not None:
            self.status = int(status)
        self.set_header("Content-Type", _CONTENT_TYPES["json"])
        self.body = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return self

    # -- whole responses ---------------------------------------------------------

    @classmethod
    def text(cls, content: str, *, status: int = 200) -> ServerResponse:
        """A complete text response.

        Args:
            content: The body.
            status: The status to answer with.
        """
        return cls(status=status).write_text(content)

    @classmethod
    def xml(cls, content: str, *, status: int = 200) -> ServerResponse:
        """A complete XML response.

        Args:
            content: The body.
            status: The status to answer with.
        """
        return cls(status=status).write_xml(content)

    @classmethod
    def json(cls, data: Any, *, status: int = 200) -> ServerResponse:
        """A complete JSON response.

        Args:
            data: What to serialize.
            status: The status to answer with.
        """
        return cls(status=status).write_json(data)

    @classmethod
    def denied(
        cls, reason: str, *, status: int = 403, **headers: str
    ) -> ServerResponse:
        """Refuse the request, as the access-control and service hooks do.

        This is the one way a hook says no (decision-52 implementation note): a
        plain text body naming the reason, the status, and ``WWW-Authenticate``
        when the caller asks for it. An access-control hook returns ``False``
        instead and the host builds this for the layer it refused.

        Args:
            reason: The plain text body naming why.
            status: The status, ``403`` unless the rule says otherwise.
            headers: Extra headers; ``www_authenticate`` becomes
                ``WWW-Authenticate``.
        """
        response = cls(status=status).write_text(reason)
        for name, value in headers.items():
            response.set_header(name.replace("_", "-"), value)
        return response

    def __repr__(self) -> str:
        return (
            f"ServerResponse({self.status} {self.status_message}, "
            f"{len(self.body)} bytes)"
        )
