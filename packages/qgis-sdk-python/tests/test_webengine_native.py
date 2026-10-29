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
TASK-23 headless harness qualified (the WebEngine smoke test).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from native_support import LoopbackOrigin, pump, serve, settle

# The webengine layer. The offscreen platform, the Chromium flags and the
# bindings path are prepared by tests/conftest.py before this module loads.
pytestmark = pytest.mark.webengine

try:
    from PyQt6 import sip
    from PyQt6.QtCore import QUrl
    from qgis_sdk.adapters.webengine import (
        BrowserPolicy,
        Decision,
        create_restricted_page,
    )
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(
        f"native WebEngine needs Qt WebEngine: {error}", allow_module_level=True
    )


@pytest.fixture(scope="module")
def allowed() -> Iterator[LoopbackOrigin]:
    yield from serve()


@pytest.fixture(scope="module")
def blocked() -> Iterator[LoopbackOrigin]:
    yield from serve()


@pytest.fixture(scope="module")
def app(qt_app):
    """The session's one application (see ``tests/layers.py``)."""
    return qt_app


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
def profile(webengine_profile):
    """The session's one profile (see ``tests/conftest.py``): pages come and go."""
    return webengine_profile


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
    app, make_page, allowed: LoopbackOrigin, blocked: LoopbackOrigin
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
    app, make_page, allowed: LoopbackOrigin, blocked: LoopbackOrigin
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
    app, make_page, allowed: LoopbackOrigin, blocked: LoopbackOrigin
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
    app, make_page, tmp_path: Path, allowed: LoopbackOrigin, blocked: LoopbackOrigin
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
