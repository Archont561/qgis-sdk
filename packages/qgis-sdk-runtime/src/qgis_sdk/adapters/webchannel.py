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


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_create_channel_o_p1(_s):
    _s.classes = _import_webchannel()
    if _s.classes is None:
        raise QgisSdkOptionalDependencyError(
            WEBCHANNEL_DEPENDENCY, WEBCHANNEL_INSTALLATION_HINT
        )
    _s.qobject, _s.pyqt_signal, _s.pyqt_slot = _s.classes


def _make_bridge_channel_object(state):
    """Build the one QObject a page may see, from the imported Qt classes."""

    class BridgeChannelObject(state.qobject):  # type: ignore[misc, valid-type]
        """The one object a page may see."""

        message = state.pyqt_signal(str)

        def __init__(self, transport: ChannelTransport) -> None:
            super().__init__(state.parent)
            self._transport = transport

        @state.pyqt_slot(str)
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

    return BridgeChannelObject


def _cc_create_channel_o_p2(_s):
    _s.BridgeChannelObject = _make_bridge_channel_object(_s)


def _cc_create_channel_o_p3(_s):

    _s.transport = ChannelTransport(
        dispatcher=_s.dispatcher, binding=_s.binding, send=lambda text: None
    )
    return _CcReturn(
        _create_channel_object_phase1(_s.BridgeChannelObject, _s.transport)
    )


def _create_channel_object_phase1(BridgeChannelObject, transport):
    channel = BridgeChannelObject(transport)
    # The signal only exists once Qt has built the class, so the transport is
    # rebound to it here instead of being handed a callable that does not exist
    # yet.
    transport.send = channel.message.emit
    return channel


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
            module = __import__(
                module_name, fromlist=("QObject", "pyqtSignal", "pyqtSlot")
            )
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
    "Return a ``QObject`` with a ``message`` signal and a ``receive`` slot.\n\n    Register it with the page's ``QWebChannel`` on the Python side, and connect\n    ``message`` to the JavaScript object's ``receive`` on the other. Every call,\n    reply, event frame and terminal frame then crosses as text; nothing else is\n    exposed, so a page cannot reach past the dispatcher.\n\n    Frames are pushed when a message arrives - the dispatcher is drained right\n    after each call - which means a stream that produces events on its own (a\n    Qt task's progress) needs whoever owns that task to call\n    :meth:`ChannelTransport.flush`. That call is deliberate: a timer is a policy\n    decision for the host, not for the SDK.\n"
    _s = _CcState(dispatcher=dispatcher, binding=binding, parent=parent)
    for _p in (
        _cc_create_channel_o_p1,
        _cc_create_channel_o_p2,
        _cc_create_channel_o_p3,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


__all__ = [
    "WEBCHANNEL_DEPENDENCY",
    "create_channel_object",
    "require_webchannel",
    "webchannel_available",
]
