"""GitHub release REST plumbing."""

import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest
from qgis_sdk_release.errors import QgisSdkReleaseError
from qgis_sdk_release.github import create_release, upload_asset


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def _opener(captured, payload=None, error=None):
    def opener(req):
        captured.append(req)
        if error is not None:
            raise error
        return FakeResponse(json.dumps(payload).encode())

    return opener


def test_create_release_request_shape():
    captured = []
    result = create_release(
        "owner/repo",
        "tok",
        "v0.1.0-rc.1",
        "v0.1.0-rc.1",
        "body text",
        prerelease=True,
        opener=_opener(captured, {"upload_url": "https://x{?name}", "html_url": "h"}),
    )
    (req,) = captured
    assert req.full_url == "https://api.github.com/repos/owner/repo/releases"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer tok"
    assert req.get_header("Content-type") == "application/json"
    payload = json.loads(req.data)
    assert payload == {
        "tag_name": "v0.1.0-rc.1",
        "name": "v0.1.0-rc.1",
        "body": "body text",
        "draft": False,
        "prerelease": True,
        "make_latest": "false",
    }
    assert result["html_url"] == "h"


def test_create_release_stable_marks_latest():
    captured = []
    create_release(
        "o/r",
        "t",
        "v1.0.0",
        "v1.0.0",
        "b",
        prerelease=False,
        opener=_opener(captured, {"upload_url": "https://x"}),
    )
    payload = json.loads(captured[0].data)
    assert payload["make_latest"] == "true" and payload["prerelease"] is False


def test_upload_asset_quotes_name_and_sends_bytes(tmp_path):
    asset = tmp_path / "qgis_sdk-0.1.0-py3-none-any.whl"
    asset.write_bytes(b"wheel-bytes")
    captured = []
    upload_asset(
        "https://uploads.github.com/repos/o/r/releases/1/assets{?name,label}",
        "tok",
        asset,
        opener=_opener(captured, {"name": asset.name}),
    )
    (req,) = captured
    assert req.full_url == (
        "https://uploads.github.com/repos/o/r/releases/1/assets"
        "?name=qgis_sdk-0.1.0-py3-none-any.whl"
    )
    assert req.data == b"wheel-bytes"
    assert req.get_header("Content-type") == "application/octet-stream"


def test_http_errors_become_release_errors():
    error = HTTPError(
        "https://api.github.com/repos/o/r/releases",
        422,
        "Unprocessable Entity",
        {},
        io.BytesIO(b'{"message": "already_exists"}'),
    )
    with pytest.raises(QgisSdkReleaseError, match="already_exists"):
        create_release(
            "o/r", "t", "v1.0.0", "v1.0.0", "b", False, opener=_opener([], error=error)
        )


def test_upload_asset_missing_file_raises(tmp_path):
    with pytest.raises((QgisSdkReleaseError, OSError)):
        upload_asset("https://x{?name}", "t", Path(tmp_path / "ghost.whl"))
