from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import (
    QEventLoop,
    QObject,
    QTimer,
    QUrl,
    pyqtSignal,
)
from qgis.PyQt.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
)

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    NetworkRequest,
    QgisSdkBlockingOnGuiThreadError,
    QgisSdkNetworkError,
    Response,
)
from qgis_sdk.services import Deliver

from ._follow_state import (
    CcReturn,
    CcState,
    ExchangeMixin1,
    cc_follow_p1,
    cc_follow_p2,
    cc_follow_p3,
    on_gui_thread,
)


class __ExchangeMixin2:
    def _follow(
        self, reply: QNetworkReply, status: int, location: QUrl
    ) -> QgisSdkNetworkError | None:
        _s = CcState(self=self, reply=reply, status=status, location=location)
        for _p in (cc_follow_p1, cc_follow_p2, cc_follow_p3):
            _r = _p(_s)
            if isinstance(_r, CcReturn):
                return _r.value
        return None

    def _error(
        self, kind: type[QgisSdkNetworkError], message: str
    ) -> QgisSdkNetworkError:
        return kind(message, method=self._method, url=self._request.url)

    def _settle(self, outcome: Response | QgisSdkNetworkError) -> None:
        if self._delivered:
            return
        self._delivered = True
        self._on_done(self)
        self._deliver(outcome)


class _Exchange(ExchangeMixin1, __ExchangeMixin2, QObject):
    """One request from first hop to delivered outcome.

    A ``QObject`` so that it has a thread: every reply it owns lives on the
    thread that started it, and a cancellation coming from another thread (a
    scope closing on the GUI thread while a blocking request runs on a worker)
    is queued to that thread instead of touching the reply directly.
    """

    _cancel_requested = pyqtSignal()

    def __init__(
        self,
        manager: QNetworkAccessManager,
        request: NetworkRequest,
        deliver: Deliver,
        on_done: Callable[[_Exchange], None],
    ) -> None:
        super().__init__()
        self._manager = manager
        self._request = request
        self._deliver = deliver
        self._on_done = on_done
        self._reply: QNetworkReply | None = None
        self._timer: QTimer | None = None
        self._hops = 0
        self._delivered = False
        self._cancelled = False
        self._timed_out = False
        self._too_large = False
        self._headers = request.headers
        self._auth_config = request.auth_config
        self._method = request.method
        self._body = request.body
        self._cancel_requested.connect(self._cancel_now)

    #: The methods QNetworkAccessManager sends through an accessor of its own,
    #: and whether that accessor takes the body. Everything else, including a
    #: GET or a DELETE that carries one, goes through ``sendCustomRequest``.
    _ACCESSORS: ClassVar[dict[str, tuple[str, bool]]] = {
        "HEAD": ("head", False),
        "POST": ("post", True),
        "PUT": ("put", True),
    }


class NativeNetworkTransport:
    """``NetworkTransport`` over ``QgsNetworkAccessManager``.

    One per owner scope: closing the scope aborts whatever is in flight. The
    manager defaults to the QGIS instance of the calling thread, which is how
    proxy, auth and certificate settings are inherited; pass one explicitly only
    in tests.
    """

    def __init__(
        self,
        scope: ResourceScope,
        *,
        manager: QNetworkAccessManager | None = None,
    ) -> None:
        self._scope = scope
        self._manager = manager
        self._active: set[_Exchange] = set()
        scope.on_close(self._abort_all)

    @property
    def in_flight(self) -> int:
        """Exchanges started and not yet delivered."""
        return len(self._active)

    def send(self, request: NetworkRequest, deliver: Deliver) -> Callable[[], None]:
        """Start the request on this thread's manager; deliver on this thread."""
        exchange = _Exchange(
            self._manager_for_thread(), request, deliver, self._active.discard
        )
        self._active.add(exchange)
        exchange.start()
        return exchange.cancel

    def send_blocking(self, request: NetworkRequest) -> Response:
        """Run the exchange under a local event loop; never on the GUI thread."""
        if on_gui_thread():
            raise QgisSdkBlockingOnGuiThreadError(
                method=request.method, url=request.url
            )
        loop = QEventLoop()
        outcomes: list[Response | Exception] = []

        def deliver(outcome: Response | Exception) -> None:
            outcomes.append(outcome)
            loop.quit()

        self.send(request, deliver)
        if not outcomes:
            loop.exec()
        outcome = outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _manager_for_thread(self) -> QNetworkAccessManager:
        return (
            self._manager
            if self._manager is not None
            else QgsNetworkAccessManager.instance()
        )

    def _abort_all(self) -> None:
        for exchange in tuple(self._active):
            exchange.cancel()
