"""Per-view network grants: origins, methods, host authentication, redirects.

A grant is what the host gives a view instead of the network. The tests pin
the rules decision-20 asks for - explicit origins, explicit methods, host
authentication only when granted, redirects only within the grant - on the
pure model, and on the fake transport that the QGIS-free suite runs against.
"""

from __future__ import annotations

import pytest
from qgis_sdk.models import (
    DEFAULT_MAX_BODY_BYTES,
    DEFAULT_MAX_REDIRECTS,
    Headers,
    NetworkRequest,
    QgisSdkGrantRefusedError,
    QgisSdkRedirectError,
    Response,
)
from qgis_sdk.network import NetworkGrant, origin_of
from qgis_sdk.network.grants import GRANT_MAX_BODY_BYTES, QgisSdkGrantError
from qgis_sdk.testing import FakeNetworkTransport

API = "https://api.example.org"


def _request(url: str, method: str = "GET", **changes) -> NetworkRequest:
    return NetworkRequest(method=method, url=url, **changes)


# -- origins ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("https://API.Example.org/collections?x=1", "https://api.example.org"),
        ("https://api.example.org:443/", "https://api.example.org"),
        ("http://api.example.org:80/", "http://api.example.org"),
        ("http://127.0.0.1:8080/ok", "http://127.0.0.1:8080"),
        ("https://[::1]:8443/", "https://[::1]:8443"),
    ],
)
def test_an_origin_is_scheme_host_and_non_default_port(url: str, origin: str) -> None:
    assert origin_of(url) == origin


@pytest.mark.parametrize(
    "url", ["", "api.example.org", "ftp://files.example.org", "https://", "file:///etc"]
)
def test_a_url_without_an_http_origin_has_none(url: str) -> None:
    assert origin_of(url) is None


def test_a_grant_normalises_its_origins_and_refuses_what_is_not_one() -> None:
    grant = NetworkGrant(origins=("HTTPS://Api.Example.org:443",))
    assert grant.origins == frozenset({"https://api.example.org"})

    with pytest.raises(QgisSdkGrantError, match="origin"):
        NetworkGrant(origins=("https://api.example.org/v1",))
    with pytest.raises(QgisSdkGrantError, match="origin"):
        NetworkGrant(origins=("https://user:pw@api.example.org",))
    with pytest.raises(QgisSdkGrantError, match="origin"):
        NetworkGrant(origins=("api.example.org",))
    with pytest.raises(QgisSdkGrantError, match="at least one"):
        NetworkGrant(origins=())


def test_a_grant_refuses_unknown_methods_and_non_positive_limits() -> None:
    with pytest.raises(QgisSdkGrantError, match="method"):
        NetworkGrant(origins=(API,), methods=("FETCH",))
    with pytest.raises(QgisSdkGrantError, match="max_body_bytes"):
        NetworkGrant(origins=(API,), max_body_bytes=0)
    with pytest.raises(QgisSdkGrantError, match="max_body_bytes"):
        NetworkGrant(origins=(API,), max_body_bytes=DEFAULT_MAX_BODY_BYTES + 1)
    with pytest.raises(QgisSdkGrantError, match="max_redirects"):
        NetworkGrant(origins=(API,), max_redirects=-1)
    with pytest.raises(QgisSdkGrantError, match="timeout"):
        NetworkGrant(origins=(API,), timeout_seconds=0)


def test_the_defaults_are_read_only_anonymous_and_bounded() -> None:
    grant = NetworkGrant(origins=(API,))
    assert grant.methods == frozenset({"GET", "HEAD"})
    assert grant.host_auth is False
    assert grant.max_body_bytes == GRANT_MAX_BODY_BYTES < DEFAULT_MAX_BODY_BYTES
    assert 0 < grant.max_redirects <= DEFAULT_MAX_REDIRECTS


# -- checking a request ----------------------------------------------------


def test_a_request_inside_the_grant_passes_and_is_constrained() -> None:
    grant = NetworkGrant(origins=(API,), methods=("GET", "POST"), max_redirects=3)

    constrained = grant.constrain(
        _request(
            f"{API}/collections",
            "POST",
            max_redirects=50,
            max_body_bytes=DEFAULT_MAX_BODY_BYTES,
            timeout_seconds=600,
        )
    )

    assert constrained.max_redirects == 3
    assert constrained.max_body_bytes == grant.max_body_bytes
    assert constrained.timeout_seconds == grant.timeout_seconds
    assert constrained.allowed_origins == frozenset({"https://api.example.org"})
    assert constrained.method == "POST"
    assert constrained.url == f"{API}/collections"


def test_a_request_that_asks_for_less_keeps_what_it_asked_for() -> None:
    grant = NetworkGrant(origins=(API,))
    constrained = grant.constrain(
        _request(API + "/", timeout_seconds=1.5, max_redirects=0, max_body_bytes=10)
    )
    assert constrained.timeout_seconds == 1.5
    assert constrained.max_redirects == 0
    assert constrained.max_body_bytes == 10


@pytest.mark.parametrize(
    ("request_", "reason"),
    [
        (_request("https://evil.example.org/"), "origin"),
        (_request("http://api.example.org/"), "origin"),
        (_request("https://api.example.org:8443/"), "origin"),
        (_request(f"{API}/x", "DELETE"), "method"),
        (_request(f"{API}/x", auth_config="cfg1"), "authentication"),
        (_request("not a url"), "origin"),
    ],
)
def test_a_request_outside_the_grant_is_refused_with_the_rule_it_broke(
    request_: NetworkRequest, reason: str
) -> None:
    grant = NetworkGrant(origins=(API,), methods=("GET",))

    with pytest.raises(QgisSdkGrantRefusedError, match=reason) as caught:
        grant.constrain(request_)

    assert caught.value.code == "grant_refused"


def test_host_authentication_is_only_usable_when_granted() -> None:
    grant = NetworkGrant(origins=(API,), host_auth=True)
    constrained = grant.constrain(_request(API + "/", auth_config="cfg1"))
    assert constrained.auth_config == "cfg1"


def test_a_refusal_never_echoes_credentials() -> None:
    grant = NetworkGrant(origins=(API,))
    request = _request(
        "https://evil.example.org/", headers=Headers({"Authorization": "Bearer s3cr3t"})
    )
    with pytest.raises(QgisSdkGrantRefusedError) as caught:
        grant.constrain(request)
    assert "s3cr3t" not in str(caught.value)
    assert "s3cr3t" not in repr(caught.value)


def test_allows_origin_answers_for_redirect_targets() -> None:
    grant = NetworkGrant(origins=(API, "https://cdn.example.org"))
    assert grant.allows_origin("https://cdn.example.org/tiles/1.png") is True
    assert grant.allows_origin("https://other.example.org/") is False
    assert grant.allows_origin("javascript:alert(1)") is False


# -- the fake transport honours the redirect rule ---------------------------


def test_the_fake_transport_refuses_a_redirect_that_leaves_the_grant() -> None:
    """The fake mirrors the native rule, so the suite cannot pass by accident."""
    transport = FakeNetworkTransport()
    grant = NetworkGrant(origins=(API,))
    request = grant.constrain(_request(f"{API}/old"))
    transport.expect(
        "GET",
        f"{API}/old",
        lambda _request: Response(
            url="https://elsewhere.example.org/new",
            status_code=200,
            reason="OK",
            headers=Headers(),
            content=b"moved",
        ),
    )
    outcomes: list[object] = []

    transport.send(request, outcomes.append)

    (outcome,) = outcomes
    assert isinstance(outcome, QgisSdkRedirectError)
    assert "elsewhere.example.org" in str(outcome)


def test_the_fake_transport_delivers_a_redirect_that_stays_inside() -> None:
    transport = FakeNetworkTransport()
    grant = NetworkGrant(origins=(API,))
    request = grant.constrain(_request(f"{API}/old"))
    transport.expect(
        "GET",
        f"{API}/old",
        lambda _request: Response(
            url=f"{API}/new",
            status_code=200,
            reason="OK",
            headers=Headers(),
            content=b"moved",
        ),
    )
    outcomes: list[object] = []

    transport.send(request, outcomes.append)

    (outcome,) = outcomes
    assert isinstance(outcome, Response)
    assert outcome.url == f"{API}/new"
