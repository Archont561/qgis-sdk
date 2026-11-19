"""``ctx.on(stream, callback)``: a native surface subscribes to a plugin's streams.

A page subscribes through the bridge (decision-23); a native surface has no
wire, so :class:`ViewStreams` opens the same ``@stream`` methods directly:
the method's iterator is pulled on :meth:`pump` and a
:class:`~qgis_sdk.bridge.streams.PushSource` is started with a sink that
delivers as it emits. Every event reaches the callback as a
:class:`StreamEvent` on the GUI thread; an event the view's own synchronous
action call produced carries ``echo=True`` (decision-55 point 2), so a
surface that already updated itself can skip its own echo. Subscriptions are
owned by the view's scope: closing the window disposes them.
"""

from __future__ import annotations

from ._streams import EventKind, StreamEvent, ViewStreams
from ._subscription import ViewSubscription

__all__ = ["EventKind", "StreamEvent", "ViewStreams", "ViewSubscription"]
