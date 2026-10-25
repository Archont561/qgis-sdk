"""The channel object against a real page over a real ``QWebChannel`` (TASK-7 AC 6).

``test_bridge_transport.py`` proves the text-in, text-out half with a fake
``send``; the stream state machine proves delivery order with no event loop at
all. Neither is evidence about the native binding, so this file is: a page
running in Chromium talks to the registered object through Qt's own
``qwebchannel.js``, and what it gets back is decided by the binding the host
minted - whatever identity the page writes into its messages - and ends when
the host disposes the view.

Loopback only, like ``test_webengine_native.py``; the imports are guarded the
same way so a host without WebEngine or WebChannel reports what it lacks.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from native_support import LoopbackOrigin, pump, serve, settle

pytestmark = pytest.mark.webengine

try:
    from PyQt6 import sip
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebChannel import QWebChannel
    from qgis_sdk.adapters.webchannel import create_channel_object
    from qgis_sdk.adapters.webengine import BrowserPolicy, create_restricted_page
    from qgis_sdk.bridge import BridgeOperation, Dispatcher, ViewBinding
    from qgis_sdk.bridge.streams import StreamSink
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(
        f"native WebChannel needs Qt WebEngine and WebChannel: {error}",
        allow_module_level=True,
    )

WHOAMI = BridgeOperation(id="demo.whoami", title="Report who the host says calls")
PUSH = BridgeOperation(id="demo.push", title="A stream the host pushes into")

PAGE = """<!doctype html><html><body>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
window.received = [];
window.ready = false;
new QWebChannel(qt.webChannelTransport, function (channel) {
  window.bridge = channel.objects.bridge;
  window.bridge.message.connect(function (text) {
    window.received.push(JSON.parse(text));
  });
  window.ready = true;
});
window.send = function (message) {
  window.bridge.receive(JSON.stringify(message));
};
</script>
</body></html>"""


class _Pushed:
    """A push source that keeps its sink for the test and counts its closes."""

    def __init__(self) -> None:
        self.sink: StreamSink | None = None
        self.closed = 0

    def start(self, sink: StreamSink) -> None:
        self.sink = sink

    def close(self) -> None:
        self.closed += 1


def _whoami(binding: ViewBinding, payload: Any) -> dict[str, Any]:
    return {"view_id": binding.view_id, "generation": binding.generation}


@pytest.fixture(scope="module")
def origin() -> Iterator[LoopbackOrigin]:
    yield from serve()


@pytest.fixture(scope="module")
def app(qt_app):
    return qt_app


@pytest.fixture(scope="module")
def profile(webengine_profile):
    """The session's one profile (see ``tests/conftest.py``)."""
    return webengine_profile


class _View:
    """A host-side view: a dispatcher, its binding, the channel and the page."""

    def __init__(self, app, profile, origin: LoopbackOrigin) -> None:
        self.app = app
        self.source = _Pushed()
        self.dispatcher = Dispatcher(
            description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
            authorize=lambda binding, operation: True,
        )
        self.dispatcher.register_bound(WHOAMI, _whoami)
        self.dispatcher.register_stream(PUSH, lambda payload: self.source)
        self.binding = self.dispatcher.bind(view_id="view-1", origin=origin.origin)
        self.page = create_restricted_page(
            BrowserPolicy(origins=(origin.origin,)), profile=profile
        )
        self.channel_object = create_channel_object(
            self.dispatcher, self.binding, parent=self.page
        )
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("bridge", self.channel_object)
        self.page.setWebChannel(self.channel)
        origin.page("/index.html", PAGE)
        self.page.load(QUrl(origin.url("/index.html")))
        pump(app, lambda: self.evaluate("window.ready === true") is True)

    def evaluate(self, script: str) -> Any:
        box: list[object] = []
        self.page.runJavaScript(script, box.append)
        pump(self.app, lambda: bool(box))
        return box[0]

    def send(self, message: dict[str, Any]) -> None:
        self.evaluate(f"window.send({json.dumps(message)}); true")

    def received(self) -> list[dict[str, Any]]:
        return self.evaluate("window.received")

    def wait_received(self, count: int) -> list[dict[str, Any]]:
        pump(self.app, lambda: len(self.received()) >= count)
        return self.received()

    def close(self) -> None:
        """Delete the page now, while its profile is alive (see the policy tests)."""
        sip.delete(self.page)
        settle(self.app, 0.05)


@pytest.fixture
def view(app, profile, origin: LoopbackOrigin) -> Iterator[_View]:
    instance = _View(app, profile, origin)
    yield instance
    instance.close()


def test_the_host_minted_binding_answers_not_the_identity_the_page_claims(
    view: _View,
) -> None:
    view.send(
        {
            "protocol": 1,
            "call_id": "c1",
            "operation": "demo.whoami",
            "view_id": "view-2",
            "generation": 99,
            "payload": {"view_id": "view-2", "generation": 99},
        }
    )

    (reply,) = view.wait_received(1)

    assert reply["call_id"] == "c1"
    assert reply["ok"] is True
    assert reply["value"] == {"view_id": "view-1", "generation": 0}


def test_a_message_that_is_not_an_envelope_is_counted_and_answered_nothing(
    view: _View,
) -> None:
    view.evaluate('window.bridge.receive("not json"); true')
    view.evaluate("window.bridge.receive(JSON.stringify([1, 2])); true")
    settle(view.app, 0.2)

    assert view.received() == []
    view.send({"protocol": 1, "call_id": "c2", "operation": "demo.whoami"})
    (reply,) = view.wait_received(1)
    assert reply["ok"] is True


def test_host_pushed_frames_reach_the_page_in_order_and_disposal_ends_them(
    view: _View,
) -> None:
    view.send(
        {"protocol": 1, "kind": "subscribe", "call_id": "s1", "operation": "demo.push"}
    )
    (ack,) = view.wait_received(1)
    assert ack["ok"] is True
    subscription_id = ack["value"]["subscription_id"]
    sink = view.source.sink
    assert sink is not None, "the dispatcher did not start the push source"

    # Pushed from the host side: nothing on the page asked, the sink's wake-up
    # flushed the frames through the channel's signal.
    for index in range(3):
        assert sink.emit({"index": index}) is True
    frames = view.wait_received(4)[1:]

    assert [frame["subscription_id"] for frame in frames] == [subscription_id] * 3
    assert [frame["seq"] for frame in frames] == [0, 1, 2]
    assert [frame["event"]["payload"]["index"] for frame in frames] == [0, 1, 2]

    # The host disposes the view: the subscription is gone, the source behind it
    # was closed exactly once, and a late reply from that source goes nowhere.
    disposed = view.channel_object.dispose()

    assert disposed == 1
    assert view.dispatcher.subscriptions() == ()
    assert view.source.closed == 1
    assert sink.emit({"index": 3}) is False
    settle(view.app, 0.2)
    assert len(view.received()) == 4
    assert view.channel_object.dispose() == 0


def test_deleting_the_page_takes_the_channel_object_with_it(
    app, profile, origin: LoopbackOrigin
) -> None:
    """The object is parented to the page, so a page that goes away does not
    leave a live slot behind for Qt to call into."""
    instance = _View(app, profile, origin)
    channel_object = instance.channel_object
    instance.channel_object.dispose()

    instance.close()

    assert sip.isdeleted(channel_object)
