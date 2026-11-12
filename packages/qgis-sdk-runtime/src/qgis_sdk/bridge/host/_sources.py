"""The push sources behind the streaming operations and the open edit sessions."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from qgis_sdk.bridge.host._support import response_event
from qgis_sdk.bridge.streams import StreamSink
from qgis_sdk.models import (
    CanvasExtent,
    Geometry,
    NetworkRequest,
    ProjectChange,
    QgisSdkResponseTooLargeError,
    Response,
)
from qgis_sdk.models.errors import QgisSdkUnknownHandleError
from qgis_sdk.services.canvas import Canvas
from qgis_sdk.services.features import EditingSession, Features
from qgis_sdk.services.network import NetworkTransport
from qgis_sdk.services.project import Project

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


class WatchProject:
    """The push source behind ``project.changed``.

    The project calls back whenever it changes, and the sink turns each frame
    into one ``data`` event; the frames are the project's own order, which is
    the order a page re-reads in. Disposal before the first change cancels the
    subscription, so a closed page leaves no listener behind.
    """

    def __init__(self, project: Project) -> None:
        self._project = project
        self._cancel: Callable[[], None] | None = None
        self._done = False

    def start(self, sink: StreamSink) -> None:
        def deliver(change: ProjectChange) -> None:
            sink.emit(change.to_wire())

        # The stream does not complete: a page follows the project until it
        # unsubscribes, so only disposal or an error ends it.
        self._cancel = self._project.watch_changes(deliver)

    def close(self) -> None:
        if self._done or self._cancel is None:
            return
        self._done = True
        self._cancel()


class WatchExtent:
    """The push source behind ``canvas.extent_changed``.

    The canvas calls back whenever the user moves it, and the sink turns each
    extent into one ``data`` frame; the frames are the canvas's order, which is
    the order a page draws them in. Disposal before the first pan cancels the
    subscription on the canvas, so a closed page leaves no listener behind.
    """

    def __init__(self, canvas: Canvas) -> None:
        self._canvas = canvas
        self._cancel: Callable[[], None] | None = None
        self._done = False

    def start(self, sink: StreamSink) -> None:
        def deliver(extent: CanvasExtent) -> None:
            sink.emit(extent.to_wire())

        # The stream does not complete: a page follows the map until it
        # unsubscribes, so only disposal or an error ends it.
        self._cancel = self._canvas.watch_extent(deliver)

    def close(self) -> None:
        if self._done or self._cancel is None:
            return
        self._done = True
        self._cancel()


class Capture:
    """The push source behind ``canvas.capture``: one drawing, one geometry.

    The tool takes as long as the user takes, so the frame arrives on a later
    event loop turn and the subscription completes as soon as it does. A
    cancelled drawing - Escape, or a view that went away - ends the subscription
    as cancelled; either way the map tool is removed by the canceller.
    """

    def __init__(self, canvas: Canvas, shape: str) -> None:
        self._canvas = canvas
        self._shape = shape
        self._cancel: Callable[[], None] | None = None
        self._done = False

    def start(self, sink: StreamSink) -> None:
        def deliver(geometry: Geometry) -> None:
            self._done = True
            if sink.emit(geometry.to_wire()):
                sink.complete()

        self._cancel = self._canvas.capture(self._shape, deliver)

    def close(self) -> None:
        if self._done or self._cancel is None:
            return
        self._done = True
        self._cancel()


class EditingSessions:
    """The host's editing sessions, scoped to the view that opened them.

    A session is a buffer over a layer, so it is neither the service's nor the
    page's: it belongs to the view. Every session records its view, a call names
    its session id, and the dispatcher disposes what a closing view held, so a
    page that disappears mid-edit cannot leave a buffer open. Two views editing
    one layer are two sessions over one provider buffer, which the service is
    free to refuse - the host does not pretend otherwise.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, EditingSession]] = {}

    def begin(
        self, binding: ViewBinding, service: Features, layer_id: str
    ) -> EditingSession:
        session = service.begin_edit(layer_id)
        self._sessions[session.id] = (binding.view_id, session)
        return session

    def require(self, binding: ViewBinding, session_id: str) -> EditingSession:
        entry = self._sessions.get(session_id)
        if entry is None or entry[0] != binding.view_id:
            # A session begun by another view is reported exactly like one that
            # never existed: the reply must not become an oracle for other views.
            raise QgisSdkUnknownHandleError(
                f"editing session {session_id!r} is not open for this view"
            )
        return entry[1]

    def close(self, session_id: str) -> bool:
        entry = self._sessions.pop(session_id, None)
        if entry is None:
            return False
        entry[1].close()
        return True

    def close_view(self, view_id: str) -> None:
        for session_id, (owner, _session) in list(self._sessions.items()):
            if owner == view_id:
                self.close(session_id)


class Fetch:
    """The push source behind ``network.fetch``: one request, one event, done.

    The transport delivers on a later event-loop turn; the sink wakes the
    view's channel. Disposal before delivery cancels the request, and a reply
    that lands after disposal writes into a closed sink, which is nothing.
    """

    def __init__(self, transport: NetworkTransport, request: NetworkRequest) -> None:
        self._transport = transport
        self._request = request
        self._cancel: Callable[[], None] | None = None
        self._done = False

    def start(self, sink: StreamSink) -> None:
        request = self._request

        def deliver(outcome: Response | Exception) -> None:
            self._done = True
            if isinstance(outcome, Response):
                if len(outcome.content) > request.max_body_bytes:
                    sink.fail(
                        QgisSdkResponseTooLargeError(
                            request.max_body_bytes,
                            method=request.method,
                            url=outcome.url,
                        )
                    )
                    return
                if sink.emit(response_event(outcome)):
                    sink.complete()
                return
            sink.fail(outcome)

        self._cancel = self._transport.send(request, deliver)

    def close(self) -> None:
        if self._done or self._cancel is None:
            return
        self._done = True
        self._cancel()
