"""The Qt half of decision-51: grab a surface and pair it with its tree.

The tree itself is pure (:func:`qgis_sdk.ui.snapshot.surface_snapshot`); only
the PNG needs Qt, and this module is the adapter layer that may import it. The
import is inside the function so the module loads without QGIS.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.snapshot import canonical_json, surface_snapshot

__all__ = ["SurfaceCapture", "capture_surface"]


@dataclass(frozen=True, slots=True)
class SurfaceCapture:
    """One surface as the decision-51 tree, with the PNG captured beside it."""

    tree: dict[str, Any]
    png: bytes | None = None

    @property
    def text(self) -> str:
        """The canonical rendering of the tree: the text an approval stores."""
        return canonical_json(self.tree)

    def write(self, stem: Path) -> tuple[Path, Path | None]:
        """Write ``<stem>.json`` and, when one was captured, ``<stem>.png``."""
        json_path = stem.with_suffix(".json")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(self.text, encoding="utf-8")
        if self.png is None:
            return json_path, None
        png_path = stem.with_suffix(".png")
        png_path.write_bytes(self.png)
        return json_path, png_path


def capture_surface(
    surface: object,
    *,
    surface_id: str,
    kind: str,
    title: str | None = None,
    declared: Sequence[str] = (),
    screenshot: bool = True,
    palette: Mapping[str, str] | None = None,
) -> SurfaceCapture:
    """Snapshot one opened surface, grabbing it when a screenshot is wanted.

    The grab happens on the caller's thread, which must be the GUI thread: the
    host calls this from the owner thread, and a test under the offscreen QPA
    gets the same pixels.
    """
    png: bytes | None = None
    digest: str | None = None
    scale = 1.0
    if screenshot:
        png, scale = _grab(surface)
        digest = "sha256:" + hashlib.sha256(png).hexdigest()
    tree = surface_snapshot(
        surface,
        surface_id=surface_id,
        kind=kind,
        title=title,
        declared=declared,
        screenshot=digest,
        scale=scale,
        palette=palette,
    )
    return SurfaceCapture(tree=tree, png=png)


def _grab(surface: Any) -> tuple[bytes, float]:
    """Encode ``surface.grab()`` as PNG and report its device pixel ratio."""
    from qgis.PyQt.QtCore import QBuffer, QIODevice

    grab = getattr(surface, "grab", None)
    if not callable(grab):
        raise QgisSdkUiError(
            f"a screenshot needs a QWidget, got {type(surface).__name__}"
        )
    pixmap = grab()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not pixmap.save(buffer, "PNG"):
            raise QgisSdkUiError("could not encode the surface screenshot as PNG")
        return bytes(buffer.data()), float(pixmap.devicePixelRatio() or 1.0)
    finally:
        buffer.close()
