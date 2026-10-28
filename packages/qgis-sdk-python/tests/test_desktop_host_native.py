"""``host()`` opening the page it was told about, inside a real QGIS (TASK-64).

``test_desktop_host.py`` proves the host without Qt: the plugin runs, the page
is remembered, nothing opens. This file is the other half, against a headless
``QgsApplication`` and a real ``QWebEngineView``: the page declared by
``[tool.qgis-sdk.web]`` is shown as a dock or a dialog, the plugin's own
action answers over ``QWebChannel``, a host operation the project granted
answers from the same channel, and one it did not grant is not there at all -
the grant list narrows the surface, it does not refuse later (AC 2, AC 5).

The page is hand-written on ``qwebchannel.js`` so the evidence is about the
host, not about the TypeScript client (which ``test_scaffold_web_native.py``
qualifies end to end).
"""

from __future__ import annotations

import json
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from native_support import pump, settle

pytestmark = pytest.mark.webengine

try:
    from PyQt6.QtCore import QCoreApplication, Qt

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    import PyQt6.QtWebEngineWidgets  # noqa: F401  (must precede the application)
    from qgis_sdk.adapters.desktop import host
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the hosted page needs Qt WebEngine: {error}", allow_module_level=True)

PACKAGE = "granted_tools"
SPEC = f"{PACKAGE}.plugin:app"
GRANTED = "project.layer_ids"
NOT_GRANTED = "layers.list"

PLUGIN = """
from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext

app = QgisSdkPlugin(id="granted", title="Granted tools")

@app.action(id="ping", title="Ping")
def ping(ctx: PluginContext, value: int) -> int:
    return value
"""

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


@pytest.fixture(scope="module")
def project(
    tmp_path_factory: pytest.TempPathFactory, webengine_profile: Any
) -> Iterator[Path]:
    """The hosted package; asks for the session profile first (see conftest)."""
    root = tmp_path_factory.mktemp("granted")
    package = root / PACKAGE
    (package / "web").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(textwrap.dedent(PLUGIN), encoding="utf-8")
    (package / "web" / "index.html").write_text(PAGE, encoding="utf-8")
    sys.path.insert(0, str(root))
    try:
        yield root
    finally:
        sys.path.remove(str(root))
        for name in [m for m in sys.modules if m.split(".")[0] == PACKAGE]:
            del sys.modules[name]


class _Page:
    """The page inside the widget ``show_view`` returned, driven from Python."""

    def __init__(self, app: Any, widget: Any, placement: str) -> None:
        self.app = app
        view = (
            widget.widget()
            if placement == "dock"
            else widget.layout().itemAt(0).widget()
        )
        self.page = view.page()
        pump(app, lambda: self.evaluate("window.ready === true") is True)

    def evaluate(self, script: str) -> Any:
        box: list[object] = []
        self.page.runJavaScript(script, box.append)
        pump(self.app, lambda: bool(box))
        return box[0]

    def call(self, call_id: str, operation: str, payload: Any) -> dict[str, Any]:
        message = {
            "protocol": 1,
            "call_id": call_id,
            "operation": operation,
            "payload": payload,
        }
        self.evaluate(f"window.send({json.dumps(message)}); true")
        pump(
            self.app,
            lambda: any(
                r.get("call_id") == call_id for r in self.evaluate("window.received")
            ),
        )
        return next(
            r for r in self.evaluate("window.received") if r["call_id"] == call_id
        )


@pytest.mark.parametrize("placement", ["dock", "dialog"])
def test_the_declared_page_opens_and_answers_the_plugins_action(
    qgis_app: Any, project: Path, placement: str
) -> None:
    from PyQt6.QtWidgets import QDialog, QDockWidget

    desktop = host(SPEC, placement=placement)(None)
    desktop.initGui()
    try:
        widget = desktop.show_view()
        assert isinstance(widget, QDockWidget if placement == "dock" else QDialog)
        assert widget.windowTitle() == "Granted tools"
        assert desktop.show_view() is widget  # opened once, raised after that
        page = _Page(qgis_app, widget, placement)
        assert page.page.url().toLocalFile() == str(
            project / PACKAGE / "web" / "index.html"
        )

        reply = page.call("c1", "ping", {"value": 7})

        assert reply["ok"] is True
        assert reply["value"] == 7
    finally:
        desktop.unload()
        settle(qgis_app, 0.05)
    assert desktop.view is None
    assert desktop.runtime.state.value == "stopped"


def test_a_granted_host_operation_answers_and_an_ungranted_one_is_absent(
    qgis_app: Any, project: Path
) -> None:
    from qgis.core import QgsProject

    QgsProject.instance().removeAllMapLayers()
    desktop = host(SPEC, placement="dialog", grants=(GRANTED,))(None)
    desktop.initGui()
    try:
        page = _Page(qgis_app, desktop.show_view(), "dialog")

        granted = page.call("g1", GRANTED, {})
        refused = page.call("g2", NOT_GRANTED, {})

        assert granted["ok"] is True
        assert granted["value"]["items"] == []  # the real project, empty
        assert refused["ok"] is False
        assert refused["error"]["code"] == "unknown_operation"
    finally:
        desktop.unload()
        settle(qgis_app, 0.05)


def test_without_grants_no_host_operation_is_registered(
    qgis_app: Any, project: Path
) -> None:
    desktop = host(SPEC, placement="dialog")(None)
    desktop.initGui()
    try:
        page = _Page(qgis_app, desktop.show_view(), "dialog")

        reply = page.call("n1", GRANTED, {})

        assert reply["ok"] is False
        assert reply["error"]["code"] == "unknown_operation"
    finally:
        desktop.unload()
        settle(qgis_app, 0.05)
