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


class _CcState2:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn2:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_test_packaged_as_p1(_s2):
    _s2.root = _s2.tmp_path / "assets"
    _s2.root.mkdir()
    _s2.secret = _s2.tmp_path / "secret.txt"
    _s2.secret.write_text("secret", encoding="utf-8")
    _s2.secret_script = _s2.tmp_path / "secret.js"
    _s2.secret_script.write_text('window.results.outside = "leaked";', encoding="utf-8")
    (_s2.root / "ok.js").write_text('window.results.inside = "ok";', encoding="utf-8")


def _cc_test_packaged_as_p2(_s2):
    (_s2.root / "index.html").write_text(
        f"""<html><body><script>window.results = {{}};</script>
        <script src="ok.js"></script>
        <script src="{_s2.secret_script.as_uri()}"></script>
        <script src="{_s2.blocked.url("/from-file.js")}"></script>
        <script>
        fetch("{_s2.allowed.url("/from-file")}").then(r => r.text())
          .then(t => {{ window.results.granted = t; }})
          .catch(e => {{ window.results.granted = "error:" + e.message; }});
        fetch("{_s2.blocked.url("/from-file")}").then(r => r.text())
          .then(t => {{ window.results.remote = t; }})
          .catch(e => {{ window.results.remote = "error:" + e.message; }});
        </script></body></html>""",
        encoding="utf-8",
    )


def _cc_test_packaged_as_p3(_s2):
    _s2.page = _s2.make_page(
        BrowserPolicy(origins=(_s2.allowed.origin,), asset_roots=(_s2.root,))
    )
    _s2.before = list(_s2.blocked.seen)

    _s2.page.page.load(QUrl.fromLocalFile(str(_s2.root / "index.html")))
    _s2.page.wait_loaded(_s2.app)
    pump(
        _s2.app,
        lambda: (
            {"inside", "granted", "remote"}
            <= set(_s2.page.evaluate(_s2.app, "Object.keys(window.results)"))
        ),
    )


def _cc_test_packaged_as_p4(_s2):
    settle(_s2.app, 0.3)

    _s2.results = _s2.page.evaluate(_s2.app, "window.results")
    assert _s2.results["inside"] == "ok"
    assert "outside" not in _s2.results
    assert _s2.results["granted"] == "hello"
    assert "/from-file" in _s2.allowed.seen
    assert str(_s2.results["remote"]).startswith("error:")
    assert _s2.blocked.seen == _s2.before


def _cc_test_packaged_as_p5(_s2):
    _packaged_assets_load_from_facts11234567891011121314151617(
        app=_s2.app,
        blocked=_s2.blocked,
        page=_s2.page,
        root=_s2.root,
        secret=_s2.secret,
        secret_script=_s2.secret_script,
    )


class _CcState1:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn1:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_test_a_navigatio_p1(_s1):
    _s1.allowed.page("/start", "<html><body>start</body></html>")
    _s1.allowed.page("/second", "<html><body>second</body></html>")
    _s1.page = _s1.make_page(BrowserPolicy(origins=(_s1.allowed.origin,)))
    _s1.page.page.load(QUrl(_s1.allowed.url("/start")))
    _s1.page.wait_loaded(_s1.app)
    _s1.before = list(_s1.blocked.seen)

    _s1.page.page.runJavaScript(f'location.href = "{_s1.blocked.url("/nav")}"')
    pump(_s1.app, lambda: bool(_s1.page.refused("navigation")))
    settle(_s1.app, 0.3)

    assert _s1.page.page.url().toString() == _s1.allowed.url("/start")


def _cc_test_a_navigatio_p2(_s1):
    assert _s1.blocked.seen == _s1.before
    assert _s1.page.refused("navigation") == [_s1.blocked.url("/nav")]

    _s1.loads = len(_s1.page.loads)
    _s1.page.page.runJavaScript(f'location.href = "{_s1.allowed.url("/second")}"')
    _s1.page.wait_loaded(_s1.app, count=_s1.loads + 1)
    assert _s1.page.page.url().toString() == _s1.allowed.url("/second")
    assert _s1.page.loads[-1] is True

    # A data: navigation is the host's: setHtml works, the page's own is refused.
    _s1.loads = len(_s1.page.loads)
    _s1.page.page.setHtml("<html><body>host</body></html>", QUrl(_s1.allowed.url("/")))


def _cc_test_a_navigatio_p3(_s1):
    _s1.page.wait_loaded(_s1.app, count=_s1.loads + 1)
    assert _s1.page.loads[-1] is True
    # Chromium itself refuses a top-frame data: navigation from script, so the
    # policy's own rule is the second lock here; either way the page stays.
    _s1.loads = len(_s1.page.loads)
    _s1.page.page.runJavaScript('location.href = "data:text/html,<b>page</b>"')
    settle(_s1.app, 0.5)
    assert _s1.page.page.url().toString() == _s1.allowed.url("/")
    assert len(_s1.page.loads) == _s1.loads
    assert all(url != _s1.allowed.url("/") for url in _s1.page.refused("navigation"))


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_test_a_page_cann_p1(_s):
    _s.allowed.page(
        "/",
        ESCAPE_HTML.format(
            allowed=_s.allowed.origin,
            blocked=_s.blocked.origin,
            blocked_ws=_s.blocked.origin.replace("http://", "ws://"),
        ),
    )
    _s.allowed.page("/frame", "<html><body>frame</body></html>")
    _s.page = _s.make_page(BrowserPolicy(origins=(_s.allowed.origin,)))

    _s.page.page.load(QUrl(_s.allowed.url("/")))


def _cc_test_a_page_cann_p2(_s):
    _s.page.wait_loaded(_s.app)
    pump(
        _s.app,
        lambda: (
            {"allowed", "blocked", "xhr"}
            <= set(_s.page.evaluate(_s.app, "Object.keys(window.results)"))
        ),
    )
    settle(_s.app, 0.5)

    _s.results = _s.page.evaluate(_s.app, "window.results")
    assert _s.results["allowed"] == "hello"


def _cc_test_a_page_cann_p3(_s):
    assert str(_s.results["blocked"]).startswith("error:")
    assert _s.results["xhr"] == 0
    assert _s.results["opened"] == "null"
    assert _s.results.get("socket", "error") != "open"
    # The granted origin served the page, the frame and the fetch - and the
    # other one was never asked for anything, by any means.
    assert (
        "/" in _s.allowed.seen
        and "/ok" in _s.allowed.seen
        and "/frame" in _s.allowed.seen
    )
    assert _s.blocked.seen == []
    _s.refused = _s.page.refused("resource")
    for path in ("/img.png", "/evil.js", "/leak", "/xhr"):
        _s.path = path
        assert _s.blocked.url(_s.path) in _s.refused, (_s.path, _s.refused)


def _cc_test_a_page_cann_p4(_s):
    # A frame is a navigation of its own first; whichever hook saw it, it
    # was refused before any request left.
    assert _s.blocked.url("/frame") in _s.refused + _s.page.refused("navigation")
    # window.open returned null before createWindow was even consulted: the
    # page setting closes that door first, and createWindow is the second lock.
    assert _s.page.refused("window") == []
    assert (
        _s.page.page.createWindow(type(_s.page.page).WebWindowType.WebBrowserTab)
        is None
    )
    assert _s.page.refused("window") == [""]


_CC_TEXT_1 = """<!doctype html><html><body>
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


def _packaged_assets_load_from_facts11234567891011121314151617(**values):
    _packaged_assets_load_from_facts112345678910111213141516(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts112345678910111213141516(**values):
    _packaged_assets_load_from_facts1123456789101112131415(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts1123456789101112131415(**values):
    _packaged_assets_load_from_facts11234567891011121314(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts11234567891011121314(**values):
    _packaged_assets_load_from_facts112345678910111213(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts112345678910111213(**values):
    _packaged_assets_load_from_facts1123456789101112(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts1123456789101112(**values):
    _packaged_assets_load_from_facts11234567891011(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts11234567891011(**values):
    _packaged_assets_load_from_facts112345678910(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts112345678910(**values):
    _packaged_assets_load_from_facts1123456789(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts1123456789(**values):
    _packaged_assets_load_from_facts112345678(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts112345678(**values):
    _packaged_assets_load_from_facts11234567(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts11234567(**values):
    _packaged_assets_load_from_facts1123456(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts1123456(**values):
    _packaged_assets_load_from_facts112345(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts112345(**values):
    _packaged_assets_load_from_facts11234(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts11234(**values):
    _packaged_assets_load_from_facts1123(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts1123(**values):
    _packaged_assets_load_from_facts112(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts112(**values):
    _packaged_assets_load_from_facts11(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        root=values["root"],
        secret=values["secret"],
        secret_script=values["secret_script"],
    )


def _packaged_assets_load_from_facts11(**values):
    refused = values["page"].refused("resource")
    assert values["secret_script"].as_uri() in refused
    assert values["blocked"].url("/from-file.js") in refused
    _packaged_assets_load_from_facts1(
        app=values["app"],
        blocked=values["blocked"],
        page=values["page"],
        refused=refused,
        root=values["root"],
        secret=values["secret"],
    )


def _packaged_assets_load_from_facts1(**values):
    assert values["blocked"].url("/from-file") in values["refused"]
    assert (
        values["page"].page.url().toString() == (values["root"] / "index.html").as_uri()
    )

    values["page"].page.runJavaScript(f'location.href = "{values["secret"].as_uri()}"')
    pump(values["app"], lambda: bool(values["page"].refused("navigation")))
    assert values["page"].refused("navigation") == [values["secret"].as_uri()]


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


ESCAPE_HTML = _CC_TEXT_1


def test_a_page_cannot_reach_an_origin_the_policy_did_not_grant(
    app, make_page, allowed: LoopbackOrigin, blocked: LoopbackOrigin
) -> None:
    _s = _CcState(app=app, make_page=make_page, allowed=allowed, blocked=blocked)
    for _p in (
        _cc_test_a_page_cann_p1,
        _cc_test_a_page_cann_p2,
        _cc_test_a_page_cann_p3,
        _cc_test_a_page_cann_p4,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def test_a_navigation_out_of_the_policy_is_refused_and_one_inside_is_not(
    app, make_page, allowed: LoopbackOrigin, blocked: LoopbackOrigin
) -> None:
    _s1 = _CcState1(app=app, make_page=make_page, allowed=allowed, blocked=blocked)
    for _p1 in (
        _cc_test_a_navigatio_p1,
        _cc_test_a_navigatio_p2,
        _cc_test_a_navigatio_p3,
    ):
        _r1 = _p1(_s1)
        if isinstance(_r1, _CcReturn1):
            return _r1.value
    return None


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
    _s2 = _CcState2(
        app=app,
        make_page=make_page,
        tmp_path=tmp_path,
        allowed=allowed,
        blocked=blocked,
    )
    for _p2 in (
        _cc_test_packaged_as_p1,
        _cc_test_packaged_as_p2,
        _cc_test_packaged_as_p3,
        _cc_test_packaged_as_p4,
        _cc_test_packaged_as_p5,
    ):
        _r2 = _p2(_s2)
        if isinstance(_r2, _CcReturn2):
            return _r2.value
    return None
