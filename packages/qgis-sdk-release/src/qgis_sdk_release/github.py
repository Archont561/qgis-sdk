"""GitHub REST calls for creating releases and uploading assets.

The HTTP opener is injectable so tests assert request shape without network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError
from urllib.parse import quote

from .errors import QgisSdkReleaseError

__all__ = ["Opener", "create_release", "upload_asset"]

Opener = Callable[[urlrequest.Request], object]


def _default_opener(req: urlrequest.Request) -> object:
    return urlrequest.urlopen(req)


def _request(
    url: str,
    token: str,
    payload: dict | None = None,
    data: bytes | None = None,
    content_type: str | None = None,
) -> urlrequest.Request:
    body = json.dumps(payload).encode() if payload is not None else data
    req = urlrequest.Request(url, data=body, method="POST" if body else "GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    elif content_type:
        req.add_header("Content-Type", content_type)
    return req


def _read_json(opener: Opener, req: urlrequest.Request, what: str) -> dict:
    try:
        with opener(req) as response:  # type: ignore[attr-defined]
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")[:400]
        raise QgisSdkReleaseError(f"{what} failed ({error.code}): {detail}") from error


def create_release(
    slug: str,
    token: str,
    tag: str,
    name: str,
    body: str,
    prerelease: bool,
    opener: Opener | None = None,
) -> dict:
    """Create one GitHub Release and return the API response."""
    open_it = opener or _default_opener
    payload = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": prerelease,
        "make_latest": "false" if prerelease else "true",
    }
    req = _request(f"https://api.github.com/repos/{slug}/releases", token, payload)
    return _read_json(open_it, req, "GitHub release creation")


def upload_asset(
    upload_url: str,
    token: str,
    path: Path,
    opener: Opener | None = None,
) -> dict:
    """Upload one release asset through the release's upload URL template."""
    open_it = opener or _default_opener
    target = Path(path)
    base = upload_url.split("{")[0]
    req = _request(
        f"{base}?name={quote(target.name)}",
        token,
        data=target.read_bytes(),
        content_type="application/octet-stream",
    )
    return _read_json(open_it, req, f"asset upload for {target.name}")
