"""Approving a surface as a fixture: the JSON, the PNG, and the diff that fails.

The Qt capture is the host's business (tested natively); this module drives
:class:`Snapshots` with captures built by hand, so what an approval does - and
what a change does to a test - is read without starting QGIS.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from qgis_sdk.adapters.snapshot import SurfaceCapture
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk_tools.snapshots import (
    SNAPSHOTS_DIRECTORY,
    SnapshotMismatch,
    Snapshots,
    SurfaceSnapshot,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _tree(
    *,
    surface: str = "buffer_dialog",
    value: float = 0.0,
    screenshot: str | None = "sha256:" + "a" * 64,
) -> dict[str, object]:
    return {
        "surface": surface,
        "kind": "dialog",
        "title": "Buffer",
        "size": {"width": 400, "height": 300},
        "scale": 1.0,
        "screenshot": screenshot,
        "nodes": [
            {
                "id": "form/distance",
                "role": "spinbox",
                "value": value,
                "label": "Distance",
                "state": {"enabled": True},
                "geometry": {"x": 0, "y": 0, "width": 100, "height": 24},
                "declared": {"field": "distance"},
            }
        ],
        "findings": [],
    }


def _capture(**overrides) -> SurfaceCapture:
    tree = _tree(**overrides)
    return SurfaceCapture(tree=tree, png=PNG if tree["screenshot"] else None)


def _snapshots(directory: Path, **overrides) -> Snapshots:
    return Snapshots(directory, capture=lambda target, name: _capture(**overrides))


def test_the_first_capture_asks_to_be_approved(tmp_path: Path):
    snapshots = _snapshots(tmp_path)
    result = snapshots("widget", name="buffer_dialog")

    assert isinstance(result, SurfaceSnapshot)
    assert result.approved is None
    assert result.ok is False
    assert result.json_path == tmp_path / "buffer_dialog.json"
    with pytest.raises(SnapshotMismatch, match="no approved snapshot") as raised:
        snapshots.verify()
    message = str(raised.value)
    assert str(tmp_path / "buffer_dialog.json") in message
    assert "approve()" in message
    assert not (tmp_path / "buffer_dialog.json").exists(), "verify writes nothing"


def test_approve_writes_the_json_and_the_png(tmp_path: Path):
    snapshots = _snapshots(tmp_path)
    result = snapshots("widget", name="buffer_dialog")
    json_path, png_path = result.approve()

    assert json_path == tmp_path / "buffer_dialog.json"
    assert png_path == tmp_path / "buffer_dialog.png"
    assert json.loads(json_path.read_text(encoding="utf-8")) == _tree()
    assert png_path is not None and png_path.read_bytes() == PNG
    snapshots.verify()  # approving during the run is what passes it


def test_an_approved_surface_that_did_not_move_passes(tmp_path: Path):
    _snapshots(tmp_path)("widget", name="buffer_dialog").approve()
    again = _snapshots(tmp_path)("widget", name="buffer_dialog")

    assert again.approved is not None
    assert again.matches is True
    assert again.difference.identical is True
    again.directory.joinpath("__unused__")
    _snapshots(tmp_path).verify()


def test_a_structural_change_fails_with_the_readable_diff(tmp_path: Path):
    _snapshots(tmp_path)("widget", name="buffer_dialog").approve()
    changed = _snapshots(tmp_path, value=7.5)
    changed("widget", name="buffer_dialog")

    with pytest.raises(SnapshotMismatch) as raised:
        changed.verify()
    message = str(raised.value)
    assert "form/distance: value 0.0 -> 7.5" in message
    assert "buffer_dialog.json" in message


def test_a_pixel_only_change_does_not_fail(tmp_path: Path):
    _snapshots(tmp_path)("widget", name="buffer_dialog").approve()
    moved_png = _snapshots(tmp_path, screenshot="sha256:" + "b" * 64)
    result = moved_png("widget", name="buffer_dialog")

    assert result.matches is False, "the image is not the approved one"
    assert result.ok is True, "a renderer bump is not a regression"
    assert [change.field for change in result.pixels] == ["screenshot"]
    moved_png.verify()


def test_a_missing_screenshot_matches_an_approved_image(tmp_path: Path):
    """A capture taken with ``screenshot=False`` is a pixel difference only."""
    _snapshots(tmp_path)("widget", name="buffer_dialog").approve()
    snapshots = _snapshots(tmp_path, screenshot=None)
    snapshots("widget", name="buffer_dialog")

    snapshots.verify()


def test_a_capture_from_a_host_keeps_its_surface_as_the_name(tmp_path: Path):
    snapshots = _snapshots(tmp_path)
    result = snapshots(_capture())

    assert result.surface == "buffer_dialog"
    assert result.png_path == tmp_path / "buffer_dialog.png"


def test_a_widget_without_a_name_is_refused(tmp_path: Path):
    with pytest.raises(QgisSdkUiError, match="surface_id=name"):
        _snapshots(tmp_path)(object())


def test_verify_reports_every_surface_in_one_failure(tmp_path: Path):
    snapshots = _snapshots(tmp_path)
    snapshots("widget", name="buffer_dialog")
    snapshots("widget", name="results_dock")

    with pytest.raises(SnapshotMismatch) as raised:
        snapshots.verify()
    assert "buffer_dialog" in str(raised.value)
    assert "results_dock" in str(raised.value)


def test_approve_all_writes_everything_the_test_captured(tmp_path: Path):
    snapshots = _snapshots(tmp_path)
    snapshots("widget", name="buffer_dialog")
    snapshots("widget", name="results_dock")
    snapshots.approve_all()

    assert sorted(path.name for path in tmp_path.glob("*.json")) == [
        "buffer_dialog.json",
        "results_dock.json",
    ]
    snapshots.verify()


def test_the_fixture_approves_under_the_test_module_and_verifies_afterwards(
    tmp_path: Path,
):
    """The pytest fixture: a generator that verifies on the way out."""
    from qgis_sdk_tools.pytest_plugin import ui_snapshot

    request = SimpleNamespace(path=tmp_path / "test_module.py")
    fixture = ui_snapshot.__wrapped__(request)
    snapshots = next(fixture)
    assert snapshots.directory == tmp_path / SNAPSHOTS_DIRECTORY

    snapshots.capture = lambda target, name: _capture()
    result = snapshots(_capture())
    result.approve()
    with pytest.raises(StopIteration):
        next(fixture)  # the teardown verified the approval and found it right


def test_the_fixture_fails_a_test_that_left_a_surface_unapproved(tmp_path: Path):
    from qgis_sdk_tools.pytest_plugin import ui_snapshot

    request = SimpleNamespace(path=tmp_path / "test_module.py")
    fixture = ui_snapshot.__wrapped__(request)
    snapshots = next(fixture)
    snapshots(_capture())

    with pytest.raises(SnapshotMismatch, match="no approved snapshot"):
        next(fixture)
