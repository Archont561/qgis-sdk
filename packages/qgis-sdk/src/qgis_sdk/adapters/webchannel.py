"""The channel layer the page actually talks to: envelopes in, envelopes out.

The pure half lives in :mod:`qgis_sdk.bridge.transport`; this module adds the
``QObject`` a ``QWebChannel`` can register, and it imports Qt only when asked
to. A deployment without the bindings gets an actionable SDK error instead of an
import failure, which is the same rule the WebEngine adapter follows.
"""

from __future__ import annotations

from typing import Any

from qgis_sdk.bridge.dispatch import Dispatcher, ViewBinding
from qgis_sdk.bridge.transport import ChannelTransport
from qgis_sdk.models.errors import QgisSdkOptionalDependencyError

WEBCHANNEL_DEPENDENCY = "pyqt6-webchannel"
WEBCHANNEL_INSTALLATION_HINT = (
    "Install the Qt WebChannel Python bindings provided by the QGIS "
    "distribution for this platform (for example python3-pyqt6-webchannel on "
    "Debian/Ubuntu or the matching OSGeo4W/macOS package). The SDK does not "
    "download or install Qt itself."
)


def _import_webchannel() -> tuple[Any, Any, Any] | None:
    """Return ``(QObject, pyqtSignal, pyqtSlot)`` if the bindings are present."""
    candidates = ("qgis.PyQt.QtCore", "PyQt6.QtCore", "PyQt5.QtCore")
    for module_name in candidates:
        try:
            module = __import__(module_name, fromlist=("QObject", "pyqtSignal", "pyqtSlot"))
        except ImportError:
            continue
        qobject = getattr(module, "QObject", None)
        signal = getattr(module, "pyqtSignal", None)
        slot = getattr(module, "pyqtSlot", None)
        if qobject is not None and signal is not None and slot is not None:
            return qobject, signal, slot
    return None


def webchannel_available() -> bool:
    """Return whether a ``QWebChannel`` host object can be created here."""
    return _import_webchannel() is not None


def require_webchannel() -> None:
    """Raise an actionable error unless the WebChannel bindings exist."""
    if not webchannel_available():
        raise QgisSdkOptionalDependencyError(
            WEBCHANNEL_DEPENDENCY, WEBCHANNEL_INSTALLATION_HINT
        )


def create_channel_object(
    dispatcher: Dispatcher,
    binding: ViewBinding,
    *,
    parent: Any = None,
) -> Any:
    """Return a ``QObject`` with a ``message`` signal and a ``receive`` slot.

    Register it with the page's ``QWebChannel`` on the Python side, and connect
    ``message`` to the JavaScript object's ``receive`` on the other. Every call,
    reply, event frame and terminal frame then crosses as text; nothing else is
    exposed, so a page cannot reach past the dispatcher.

    Frames are pushed when a message arrives - the dispatcher is drained right
    after each call - which means a stream that produces events on its own (a
    Qt task's progress) needs whoever owns that task to call
    :meth:`ChannelTransport.flush`. That call is deliberate: a timer is a policy
    decision for the host, not for the SDK.
    """
    classes = _import_webchannel()
    if classes is None:
        raise QgisSdkOptionalDependencyError(
            WEBCHANNEL_DEPENDENCY, WEBCHANNEL_INSTALLATION_HINT
        )
    qobject, pyqt_signal, pyqt_slot = classes

    class BridgeChannelObject(qobject):  # type: ignore[misc, valid-type]
        """The one object a page may see."""

        message = pyqt_signal(str)

        def __init__(self, transport: ChannelTransport) -> None:
            super().__init__(parent)
            self._transport = transport

        @pyqt_slot(str)
        def receive(self, text: str) -> None:
            """Accept one message and answer it, frames included."""
            self._transport.receive(text)
            self.flush()

        def flush(self, limit: int = 16) -> int:
            """Push the frames waiting for this view."""
            return self._transport.flush(limit=limit)

        def dispose(self) -> int:
            """Close every subscription this view opened."""
            return self._transport.dispose()

    transport = ChannelTransport(
        dispatcher=dispatcher, binding=binding, send=lambda text: None
    )
    channel = BridgeChannelObject(transport)
    # The signal only exists once Qt has built the class, so the transport is
    # rebound to it here instead of being handed a callable that does not exist
    # yet.
    transport.send = channel.message.emit
    return channel


__all__ = [
    "WEBCHANNEL_DEPENDENCY",
    "create_channel_object",
    "require_webchannel",
    "webchannel_available",
]
