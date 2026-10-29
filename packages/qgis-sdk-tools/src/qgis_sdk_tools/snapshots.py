"""Approve a plugin's surfaces as fixtures: JSON and PNG beside the tests.

Decision-51 point 5: a test writes the surface it just showed as a capture and
leans on the SDK to compare it with the one the project approved. Structure,
values and state fail the test with the readable diff; a different PNG does
not, because a screenshot is for humans and agents and a renderer bump is not a
regression.

The approval lives under the test module's ``__snapshots__`` directory as
``<surface>.json`` (canonical, what the comparison reads) and ``<surface>.png``
(what a reader opens). :class:`Snapshots` is the whole mechanism; the pytest
fixture that hands one to a test is a few lines in
:mod:`qgis_sdk_tools.pytest_plugin`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from qgis_sdk.adapters.snapshot import SurfaceCapture, capture_surface
from qgis_sdk.models import QgisSdkUiError

from qgis_sdk_tools.ui_diff import SnapshotDiff, diff_snapshots

__all__ = ["SNAPSHOTS_DIRECTORY", "SnapshotMismatch", "Snapshots", "SurfaceSnapshot"]

SNAPSHOTS_DIRECTORY: Final = "__snapshots__"
"""Where an approval sits relative to the test module that made it."""


class SnapshotMismatch(AssertionError):
    """A surface differs from what the project approved, with the diff in the text."""


@dataclass
class SurfaceSnapshot:
    """One surface, compared with the approval it has (or has not) got yet."""

    surface: str
    capture: SurfaceCapture
    directory: Path
    approved: dict[str, Any] | None
    difference: SnapshotDiff
    approved_again: bool = False

    @property
    def json_path(self) -> Path:
        """Where the approved tree lives, whether or not it exists."""
        return self.directory / f"{self.surface}.json"

    @property
    def png_path(self) -> Path:
        """Where the approved image lives, whether or not it exists."""
        return self.directory / f"{self.surface}.png"

    @property
    def pixels(self) -> tuple[Any, ...]:
        """What changed in the image alone; never a failure on its own."""
        return self.difference.pixels

    @property
    def matches(self) -> bool:
        """True when this capture is what the project approved, image included."""
        return self.approved is not None and self.difference.identical

    @property
    def ok(self) -> bool:
        """True when the approval covers this capture; a moved PNG still counts."""
        return self.approved_again or (
            self.approved is not None and not self.difference
        )

    def approve(self) -> tuple[Path, Path | None]:
        """Write this capture as the approval; the next run compares against it."""
        written = self.capture.write(self.directory / self.surface)
        self.approved = json.loads(self.capture.text)
        self.difference = diff_snapshots(self.approved, self.capture.tree)
        self.approved_again = True
        return written

    def report(self) -> str:
        """The failure text: where the approval is, and what differs from it."""
        if self.approved is None:
            return (
                f"{self.surface}: no approved snapshot at {self.json_path}; call "
                f"ui_snapshot(...).approve() to write {self.json_path.name} and "
                f"{self.png_path.name}"
            )
        return f"{self.surface} ({self.json_path}):\n{self.difference.render()}"


Capture = Callable[[Any], SurfaceCapture]


def _capture_widget(target: Any, name: str) -> SurfaceCapture:
    """Snapshot a widget the test built or a host opened."""
    return capture_surface(target, surface_id=name, kind="widget")


@dataclass
class Snapshots:
    """The ``ui_snapshot`` factory: capture, compare, and approve on request."""

    directory: Path
    capture: Capture = _capture_widget
    results: list[SurfaceSnapshot] = field(default_factory=list)

    def __call__(self, target: Any, *, name: str | None = None) -> SurfaceSnapshot:
        """Capture ``target`` and compare it with what the project approved.

        ``target`` is a ``SurfaceCapture`` from a host - the scope-safe way to
        reach a plugin's own surface - or a widget, which is captured here. A
        screenshot the test cannot take is not a difference: pass a capture
        made with ``screenshot=False`` and the approval's image is ignored.
        """
        capture = target if isinstance(target, SurfaceCapture) else None
        surface = name or (capture.tree["surface"] if capture is not None else None)
        if surface is None:
            raise QgisSdkUiError(
                "a widget needs surface_id=name to be snapshotted; pass the "
                "SurfaceCapture a host made, or name the surface"
            )
        if capture is None:
            capture = self.capture(target, surface)
        path = self.directory / f"{surface}.json"
        approved = (
            json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        )
        difference = (
            diff_snapshots(approved, capture.tree)
            if approved is not None
            else SnapshotDiff()
        )
        result = SurfaceSnapshot(
            surface=surface,
            capture=capture,
            directory=self.directory,
            approved=approved,
            difference=difference,
        )
        self.results.append(result)
        return result

    def verify(self) -> None:
        """Fail with every unapproved or changed surface, in one readable text.

        Called by the fixture after the test, so a test can still call
        ``approve()`` on what it captured: an approval made during the run is
        what the next run compares, and this run passes.
        """
        problems = [result.report() for result in self.results if not result.ok]
        if problems:
            raise SnapshotMismatch("\n".join(problems))

    def approve_all(self) -> None:
        """Write every capture of this test as its approval."""
        for result in self.results:
            result.approve()
