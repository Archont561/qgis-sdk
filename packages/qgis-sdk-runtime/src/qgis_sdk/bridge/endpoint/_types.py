"""The types the endpoint is wired with: a view's identity, and its callables."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from qgis_sdk.bridge.streams import PushSource

Streamed = Iterator[Mapping[str, Any]] | PushSource | None
"""What a stream source hands back: a pulled iterator, a pushed source, or nothing."""


@dataclass(frozen=True, slots=True)
class ViewBinding:
    """The trusted identity of one view, minted by the host.

    Nothing here is read from the payload. A client that sends its own view id
    or generation is not disagreeing with the host, it is being ignored.
    """

    view_id: str
    origin: str
    generation: int


Handler = Callable[[Mapping[str, Any]], Any]
#: A handler that needs to know who is calling: it receives the host-minted
#: binding first, because an operation that resolves a scoped handle has to
#: check it against the caller and must never take that identity from the payload.
BoundHandler = Callable[[ViewBinding, Mapping[str, Any]], Any]
BoundStreamSource = Callable[[ViewBinding, Mapping[str, Any]], Streamed]
Authorizer = Callable[[ViewBinding, str], bool]
Waker = Callable[[], None]
ThemeProvider = Callable[[], Mapping[str, Any] | None]
"""Reads the host's palette for the handshake's ``theme``; ``None`` means no theme.

Called on every handshake, so a page that reconnects after the user switched the
QGIS theme sees the new palette. The adapter supplies one that reads
``QApplication.palette()``; the dispatcher itself never imports Qt.
"""
