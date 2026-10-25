"""Response and header values: buffered, explicit about errors, credential-safe."""

from __future__ import annotations

import pytest
from qgis_sdk.models import (
    DEFAULT_MAX_BODY_BYTES,
    DEFAULT_MAX_REDIRECTS,
    Headers,
    QgisSdkDecodeError,
    QgisSdkHttpStatusError,
    Response,
)


def _response(
    status: int = 200,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    reason: str = "OK",
) -> Response:
    return Response(
        url="https://example.test/x",
        status_code=status,
        reason=reason,
        headers=Headers(headers or {}),
        content=body,
        method="GET",
    )


def test_headers_are_case_insensitive_and_keep_the_given_names() -> None:
    headers = Headers({"Content-Type": "text/plain", "X-A": "1"})

    assert headers["content-type"] == "text/plain"
    assert headers.get("x-a") == "1"
    assert list(headers) == ["Content-Type", "X-A"]
    assert "CONTENT-TYPE" in headers
    assert len(headers) == 2


def test_merging_headers_overrides_case_insensitively_and_leaves_the_original() -> None:
    base = Headers({"Accept": "text/html", "X-Keep": "yes"})

    merged = base.merge({"accept": "application/json"})

    assert merged["Accept"] == "application/json"
    assert merged["X-Keep"] == "yes"
    assert base["Accept"] == "text/html"
    assert merged.without("x-keep") == Headers({"accept": "application/json"})


def test_header_repr_redacts_credentials() -> None:
    text = repr(
        Headers({"Authorization": "Bearer s3cret", "Cookie": "sid=1", "X": "v"})
    )

    assert "s3cret" not in text
    assert "sid=1" not in text
    assert "'X': 'v'" in text


def test_text_uses_the_declared_charset_and_falls_back_to_utf8() -> None:
    latin = _response(
        body="caf\xe9".encode("latin-1"),
        headers={"Content-Type": "text/plain; charset=latin-1"},
    )
    plain = _response(body="caf\xe9".encode())

    assert latin.encoding == "latin-1"
    assert latin.text == "caf\xe9"
    assert plain.encoding is None
    assert plain.text == "caf\xe9"


def test_undecodable_text_is_a_decode_error_naming_the_request() -> None:
    response = _response(
        body=b"\xff\xfe", headers={"Content-Type": "text/plain; charset=utf-8"}
    )

    with pytest.raises(
        QgisSdkDecodeError, match="GET https://example.test/x"
    ) as caught:
        _ = response.text
    assert caught.value.code == "decode_failed"


def test_json_parses_and_refuses_non_json() -> None:
    assert _response(body=b'{"a": [1, 2]}').json() == {"a": [1, 2]}
    with pytest.raises(QgisSdkDecodeError, match="not valid JSON"):
        _response(body=b"<html>").json()


def test_raise_for_status_is_explicit_and_keeps_the_status() -> None:
    ok = _response(200)
    not_found = _response(404, reason="Not Found")

    assert ok.raise_for_status() is ok
    assert ok.ok is True
    assert not_found.ok is False
    with pytest.raises(QgisSdkHttpStatusError, match="HTTP 404 Not Found") as caught:
        not_found.raise_for_status()
    assert caught.value.status_code == 404
    assert caught.value.code == "http_status"


def test_the_measured_limits_are_the_defaults() -> None:
    # Set from packages/qgis-sdk-python/scripts/network_limits_probe.py (see doc-15);
    # a change here needs a new measurement, not a new opinion.
    assert DEFAULT_MAX_BODY_BYTES == 16 * 1024 * 1024
    assert DEFAULT_MAX_REDIRECTS == 20
