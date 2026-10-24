"""The restricted page against a real Chromium (TASK-20, acceptance criterion 3).

``test_webengine_policy.py`` pins what the policy decides; this file proves the
two Qt hooks consult it where it matters: a page served by an allowed loopback
origin tries every ordinary way out - ``fetch``, ``<img>``, ``<script>``,
``<iframe>``, ``location``, ``window.open`` - towards a second loopback origin
the policy did not grant, and that origin must see nothing at all. The allowed
origin keeps working, so the test cannot pass by blocking everything.

Everything is loopback; nothing here contacts the internet. The imports are
guarded like ``test_network_native.py`` so a host without Qt WebEngine reports
what it lacks instead of failing collection. The Chromium flags are the ones the
TASK-23 headless harness qualified (``scripts/webengine_smoke.py``).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage --single-process",
)
_BINDINGS = Path(sys.prefix) / "share" / "qgis" / "python"
if _BINDINGS.is_dir() and str(_BINDINGS) not in sys.path:
    sys.path.insert(0, str(_BINDINGS))

try:
    from PyQt6 import sip
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineCore import QWebEngineProfile
    from PyQt6.QtWidgets import QApplication
    from qgis_sdk.adapters.webengine import (
        BrowserPolicy,
        Decision,
        create_restricted_page,
    )
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(
        f"native WebEngine needs Qt WebEngine: {error}", allow_module_level=True
    )

DEADLINE_SECONDS = 20.0


# -- loopback origins ------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        """Quiet; the test reads ``server.seen`` instead."""

    def do_GET(self) -> None:
        server = self.server
        assert isinstance(server, _Origin)
        server.seen.append(self.path)
        body, content_type = server.pages.get(
            self.path.split("?")[0], (b"hello", "text/plain")
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


class _Origin(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.seen: list[str] = []
        self.pages: dict[str, tuple[bytes, str]] = {}

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def url(self, path: str) -> str:
        return self.origin + path

    def page(self, path: str, html: str) -> None:
        self.pages[path] = (html.encode("utf-8"), "text/html; charset=utf-8")


def _serve() -> Iterator[_Origin]:
    server = _Origin()
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def allowed() -> Iterator[_Origin]:
    yield from _serve()


@pytest.fixture(scope="module")
def blocked() -> Iterator[_Origin]:
    yield from _serve()


@pytest.fixture(scope="module")
def app():
    """One headless application; reuse whatever another module started."""
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([sys.argv[0]])


def pump(app, until: Callable[[], bool], *, deadline: float = DEADLINE_SECONDS) -> None:
    end = time.monotonic() + deadline
    while not until():
        if time.monotonic() > end:
            raise AssertionError("condition not met within the deadline")
        app.processEvents()
        time.sleep(0.005)


def settle(app, seconds: float) -> None:
    """Spin the loop for a while: the absence of a request needs time to show."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


class _Page:
    """A restricted page plus what it refused and how its loads ended."""

    def __init__(self, app, profile, policy: BrowserPolicy) -> None:
        self.refusals: list[tuple[str, Decision]] = []
        self.loads: list[bool] = []
        self.page = create_restricted_page(
            policy, profile=profile, on_refusal=self._refused
        )
        self.page.loadFinished.connect(self.loads.append)
        self.console: list[str] = []
        self.page.javaScriptConsoleMessage = self._console  # type: ignore[method-assign]

    def _refused(self, kind: str, decision: Decision) -> None:
        self.refusals.append((kind, decision))

    def _console(self, level, message, line, source) -> None:
        self.console.append(str(message))

    def close(self, app) -> None:
        """Delete the page now, while its profile is alive.

        ``deleteLater`` leaves a page whose wrapper outlives the C++ object and
        the process traps at exit; a synchronous delete does not.
        """
        sip.delete(self.page)
        settle(app, 0.05)

    def refused(self, kind: str) -> list[str]:
        return [decision.url for k, decision in self.refusals if k == kind]

    def evaluate(self, app, script: str):
        box: list[object] = []
        self.page.runJavaScript(script, box.append)
        pump(app, lambda: bool(box))
        return box[0]

    def wait_loaded(self, app, count: int = 1) -> None:
        pump(app, lambda: len(self.loads) >= count)


@pytest.fixture(scope="module")
def profile(app):
    """One off-the-record profile for the module, outliving every page.

    Chromium tears a profile down once; destroying one and creating another
    in the same process aborts, so the pages come and go and this stays.
    """
    return QWebEngineProfile(app)


@pytest.fixture
def make_page(app, profile) -> Iterator[Callable[[BrowserPolicy], _Page]]:
    pages: list[_Page] = []

    def make(policy: BrowserPolicy) -> _Page:
        page = _Page(app, profile, policy)
        pages.append(page)
        return page

    yield make
    for page in pages:
        page.close(app)


ESCAPE_HTML = """<!doctype html><html><body>
<img id="img" src="{blocked}/img.png">
<script src="{blocked}/evil.js"></script>
<iframe id="frame" src="{blocked}/frame"></iframe>
<iframe id="ok-frame" src="{allowed}/frame"></iframe>
<script>
window.results = {{}};
fetch("{allowed}/ok").then(r => r.text()).then(t => {{ window.results.allowed = t; }})
  .catch(e => {{ window.results.allowed = "error:" + e.message; }});
fetch("{blocked}/leak").then(r => r.text()).then(t => {{ window.results.blocked = t; }})
  .catch(e => {{ window.results.blocked = "error:" + e.message; }});
const xhr = new XMLHttpRequest();
xhr.onloadend = () => {{ window.results.xhr = xhr.status; }};
xhr.open("GET", "{blocked}/xhr"); xhr.send();
try {{
  const socket = new WebSocket("{blocked_ws}/socket");
  socket.onerror = () => {{ window.results.socket = "error"; }};
  socket.onopen = () => {{ window.results.socket = "open"; }};
}} catch (e) {{ window.results.socket = "error:" + e.message; }}
window.results.opened = String(window.open("{blocked}/popup"));
</script>
</body></html>"""


def test_a_page_cannot_reach_an_origin_the_policy_did_not_grant(
    app, make_page, allowed: _Origin, blocked: _Origin
) -> None:
    allowed.page(
        "/",
        ESCAPE_HTML.format(
            allowed=allowed.origin,
            blocked=blocked.origin,
            blocked_ws=blocked.origin.replace("http://", "ws://"),
        ),
    )
    allowed.page("/frame", "<html><body>frame</body></html>")
    page = make_page(BrowserPolicy(origins=(allowed.origin,)))

    page.page.load(QUrl(allowed.url("/")))
    page.wait_loaded(app)
    pump(
        app,
        lambda: (
            {"allowed", "blocked", "xhr"}
            <= set(page.evaluate(app, "Object.keys(window.results)"))
        ),
    )
    settle(app, 0.5)

    results = page.evaluate(app, "window.results")
    assert results["allowed"] == "hello"
    assert str(results["blocked"]).startswith("error:")
    assert results["xhr"] == 0
    assert results["opened"] == "null"
    assert results.get("socket", "error") != "open"
    # The granted origin served the page, the frame and the fetch - and the
    # other one was never asked for anything, by any means.
    assert "/" in allowed.seen and "/ok" in allowed.seen and "/frame" in allowed.seen
    assert blocked.seen == []
    refused = page.refused("resource")
    for path in ("/img.png", "/evil.js", "/leak", "/xhr"):
        assert blocked.url(path) in refused, (path, refused)
    # A frame is a navigation of its own first; whichever hook saw it, it
    # was refused before any request left.
    assert blocked.url("/frame") in refused + page.refused("navigation")
    # window.open returned null before createWindow was even consulted: the
    # page setting closes that door first, and createWindow is the second lock.
    assert page.refused("window") == []
    assert page.page.createWindow(type(page.page).WebWindowType.WebBrowserTab) is None
    assert page.refused("window") == [""]


def test_a_navigation_out_of_the_policy_is_refused_and_one_inside_is_not(
    app, make_page, allowed: _Origin, blocked: _Origin
) -> None:
    allowed.page("/start", "<html><body>start</body></html>")
    allowed.page("/second", "<html><body>second</body></html>")
    page = make_page(BrowserPolicy(origins=(allowed.origin,)))
    page.page.load(QUrl(allowed.url("/start")))
    page.wait_loaded(app)
    before = list(blocked.seen)

    page.page.runJavaScript(f'location.href = "{blocked.url("/nav")}"')
    pump(app, lambda: bool(page.refused("navigation")))
    settle(app, 0.3)

    assert page.page.url().toString() == allowed.url("/start")
    assert blocked.seen == before
    assert page.refused("navigation") == [blocked.url("/nav")]

    loads = len(page.loads)
    page.page.runJavaScript(f'location.href = "{allowed.url("/second")}"')
    page.wait_loaded(app, count=loads + 1)
    assert page.page.url().toString() == allowed.url("/second")
    assert page.loads[-1] is True

    # A data: navigation is the host's: setHtml works, the page's own is refused.
    loads = len(page.loads)
    page.page.setHtml("<html><body>host</body></html>", QUrl(allowed.url("/")))
    page.wait_loaded(app, count=loads + 1)
    assert page.loads[-1] is True
    # Chromium itself refuses a top-frame data: navigation from script, so the
    # policy's own rule is the second lock here; either way the page stays.
    loads = len(page.loads)
    page.page.runJavaScript('location.href = "data:text/html,<b>page</b>"')
    settle(app, 0.5)
    assert page.page.url().toString() == allowed.url("/")
    assert len(page.loads) == loads
    assert all(url != allowed.url("/") for url in page.refused("navigation"))


def test_a_subframe_cannot_navigate_out_either(
    app, make_page, allowed: _Origin, blocked: _Origin
) -> None:
    allowed.page(
        "/parent",
        f"""<html><body><iframe id="f" src="{allowed.url("/child")}"></iframe>
        <script>
        window.results = {{}};
        document.getElementById("f").addEventListener("load", () => {{
          window.results.loaded = (window.results.loaded || 0) + 1;
        }});
        </script></body></html>""",
    )
    allowed.page(
        "/child",
        f"""<html><body><script>
        setTimeout(() => {{ location.href = "{blocked.url("/escape")}"; }}, 50);
        </script></body></html>""",
    )
    page = make_page(BrowserPolicy(origins=(allowed.origin,)))
    before = list(blocked.seen)

    page.page.load(QUrl(allowed.url("/parent")))
    page.wait_loaded(app)
    pump(app, lambda: bool(page.refused("navigation")))
    settle(app, 0.3)

    assert page.refused("navigation") == [blocked.url("/escape")]
    assert blocked.seen == before


def test_packaged_assets_load_from_their_root_and_from_nowhere_else(
    app, make_page, tmp_path: Path, allowed: _Origin, blocked: _Origin
) -> None:
    """A ``file:`` page: its own root, a granted origin, and nothing else."""
    root = tmp_path / "assets"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    secret_script = tmp_path / "secret.js"
    secret_script.write_text('window.results.outside = "leaked";', encoding="utf-8")
    (root / "ok.js").write_text('window.results.inside = "ok";', encoding="utf-8")
    (root / "index.html").write_text(
        f"""<html><body><script>window.results = {{}};</script>
        <script src="ok.js"></script>
        <script src="{secret_script.as_uri()}"></script>
        <script src="{blocked.url("/from-file.js")}"></script>
        <script>
        fetch("{allowed.url("/from-file")}").then(r => r.text())
          .then(t => {{ window.results.granted = t; }})
          .catch(e => {{ window.results.granted = "error:" + e.message; }});
        fetch("{blocked.url("/from-file")}").then(r => r.text())
          .then(t => {{ window.results.remote = t; }})
          .catch(e => {{ window.results.remote = "error:" + e.message; }});
        </script></body></html>""",
        encoding="utf-8",
    )
    page = make_page(BrowserPolicy(origins=(allowed.origin,), asset_roots=(root,)))
    before = list(blocked.seen)

    page.page.load(QUrl.fromLocalFile(str(root / "index.html")))
    page.wait_loaded(app)
    pump(
        app,
        lambda: (
            {"inside", "granted", "remote"}
            <= set(page.evaluate(app, "Object.keys(window.results)"))
        ),
    )
    settle(app, 0.3)

    results = page.evaluate(app, "window.results")
    assert results["inside"] == "ok"
    assert "outside" not in results
    assert results["granted"] == "hello"
    assert "/from-file" in allowed.seen
    assert str(results["remote"]).startswith("error:")
    assert blocked.seen == before
    refused = page.refused("resource")
    assert secret_script.as_uri() in refused
    assert blocked.url("/from-file.js") in refused
    assert blocked.url("/from-file") in refused
    assert page.page.url().toString() == (root / "index.html").as_uri()

    page.page.runJavaScript(f'location.href = "{secret.as_uri()}"')
    pump(app, lambda: bool(page.refused("navigation")))
    assert page.refused("navigation") == [secret.as_uri()]
