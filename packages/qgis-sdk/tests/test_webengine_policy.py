"""The browser egress policy, decided without a browser (decision-20, TASK-20).

A page inside ``QWebEngineView`` can reach the network without the bridge: a
``fetch``, an ``<img>``, an ``<iframe>``, a ``location`` change. The policy
object here is what the Qt page and its request interceptor consult; it is
pure, so every rule is pinned without Chromium, and the real-browser test in
``test_webengine_native.py`` proves the two hooks actually consult it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk.adapters.webengine import BrowserPolicy, Decision
from qgis_sdk.models import QgisSdkBridgeError

APP = "http://127.0.0.1:5173"
API = "https://api.example.org"


def _policy(tmp_path: Path, **changes) -> BrowserPolicy:
    root = tmp_path / "assets"
    root.mkdir(exist_ok=True)
    options = {"origins": (APP, API), "asset_roots": (root,)}
    options.update(changes)
    return BrowserPolicy(**options)


# -- construction -----------------------------------------------------------


def test_a_policy_normalises_origins_and_resolves_asset_roots(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    policy = BrowserPolicy(
        origins=("HTTP://127.0.0.1:5173/", "https://API.example.org:443"),
        asset_roots=(tmp_path / "assets" / ".." / "assets",),
    )
    assert policy.origins == frozenset({APP, API})
    assert policy.asset_roots == ((tmp_path / "assets").resolve(),)


def test_a_policy_refuses_what_is_not_an_origin_or_not_a_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(QgisSdkBridgeError, match="origin"):
        BrowserPolicy(origins=("example.org",))
    with pytest.raises(QgisSdkBridgeError, match="origin"):
        BrowserPolicy(origins=("https://api.example.org/v1",))
    with pytest.raises(QgisSdkBridgeError, match="directory"):
        BrowserPolicy(asset_roots=(tmp_path / "missing",))


def test_the_empty_policy_allows_only_the_host_s_own_content(tmp_path: Path) -> None:
    policy = BrowserPolicy()
    assert policy.resource("qrc:/qgis_sdk/app/index.js").allowed is True
    assert policy.resource("about:blank").allowed is True
    assert policy.resource(f"{API}/x").allowed is False
    assert policy.navigation(f"{APP}/").allowed is False


# -- resources ---------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        f"{APP}/assets/index.js",
        f"{APP}/@vite/client",
        f"{API}/collections?limit=1",
        "HTTPS://API.EXAMPLE.ORG/upper",
        "ws://127.0.0.1:5173/",
        "wss://api.example.org/live",
        "qrc:/qgis_sdk/app/index.html",
        "about:blank",
        "about:srcdoc",
        "data:image/png;base64,iVBORw0KGgo=",
        f"blob:{APP}/4f1c2c7e-1b2d-4a3e-9c4f-5d6e7f8a9b0c",
    ],
)
def test_a_resource_inside_the_policy_is_allowed(tmp_path: Path, url: str) -> None:
    decision = _policy(tmp_path).resource(url)
    assert decision.allowed is True, decision.reason


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.org/",
        "http://api.example.org/",  # scheme is part of the origin
        "https://api.example.org:8443/",  # and so is the port
        "https://api.example.org.evil.net/",  # no suffix matching
        "http://127.0.0.1:5174/",
        "ws://evil.example.org/",
        "blob:https://evil.example.org/uuid",
        "ftp://files.example.org/",
        "javascript:alert(1)",
        "chrome://settings",
        "devtools://devtools/bundled/inspector.html",
        "chrome-extension://abcdef/x.js",
        "file:///etc/passwd",
        "",
        "not a url",
    ],
)
def test_a_resource_outside_the_policy_is_refused_with_a_reason(
    tmp_path: Path, url: str
) -> None:
    decision = _policy(tmp_path).resource(url)
    assert decision.allowed is False
    assert decision.reason


def test_a_file_resource_is_allowed_only_under_an_asset_root(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    root = tmp_path / "assets"
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    inside = root / "index.html"

    assert policy.resource(inside.as_uri()).allowed is True
    assert policy.resource((root / "missing.js").as_uri()).allowed is True
    outside = tmp_path / "secret.txt"
    assert policy.resource(outside.as_uri()).allowed is False
    traversal = f"{root.as_uri()}/../secret.txt"
    assert policy.resource(traversal).allowed is False
    encoded = f"{root.as_uri()}/%2e%2e/secret.txt"
    assert policy.resource(encoded).allowed is False
    sibling = tmp_path / "assets-evil" / "x.js"
    assert policy.resource(sibling.as_uri()).allowed is False


def test_a_file_resource_through_a_symlink_out_of_the_root_is_refused(
    tmp_path: Path,
) -> None:
    policy = _policy(tmp_path)
    root = tmp_path / "assets"
    secret = tmp_path / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    try:
        (root / "link.txt").symlink_to(secret)
    except (OSError, NotImplementedError):  # pragma: no cover - platform policy
        pytest.skip("symlinks are not permitted here")
    assert policy.resource((root / "link.txt").as_uri()).allowed is False


# -- navigation --------------------------------------------------------------


def test_navigation_follows_the_same_origins_and_roots(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    assert policy.navigation(f"{APP}/panel").allowed is True
    assert policy.navigation(f"{API}/docs").allowed is True
    assert policy.navigation("https://evil.example.org/").allowed is False
    assert policy.navigation((tmp_path / "assets" / "index.html").as_uri()).allowed
    assert policy.navigation("file:///etc/passwd").allowed is False
    assert policy.navigation("about:blank").allowed is True
    assert policy.navigation("about:srcdoc").allowed is True
    assert policy.navigation("qrc:/qgis_sdk/app/index.html").allowed is True


def test_a_data_url_navigation_is_the_host_s_to_make_and_not_the_page_s(
    tmp_path: Path,
) -> None:
    """``setHtml`` arrives as a typed ``data:`` navigation; a page's does not."""
    policy = _policy(tmp_path)
    url = "data:text/html;charset=UTF-8,%3Chtml%3E%3C%2Fhtml%3E"
    assert policy.navigation(url, host_initiated=True).allowed is True
    refused = policy.navigation(url)
    assert refused.allowed is False
    assert "host" in refused.reason


def test_a_blob_navigation_keeps_its_creator_s_origin(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    assert policy.navigation(f"blob:{APP}/uuid").allowed is True
    assert policy.navigation("blob:https://evil.example.org/uuid").allowed is False
    assert policy.navigation("blob:null/uuid").allowed is False


def test_a_decision_says_what_it_decided_about(tmp_path: Path) -> None:
    decision = _policy(tmp_path).resource("https://evil.example.org/x?token=1")
    assert isinstance(decision, Decision)
    # The query is where a token would be; a decision is made to be logged.
    assert decision.url == "https://evil.example.org/x"
    assert "https://evil.example.org" in decision.reason
    assert "token" not in decision.reason
