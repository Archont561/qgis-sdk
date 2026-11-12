"""Poll the plugin's Python sources for changes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from qgis_sdk_tools.paths import walk_files

from ._types import UNWATCHED

__all__ = ["SourceWatcher"]


class SourceWatcher:
    """Poll the plugin's Python sources for changes.

    Polling, not inotify: it is portable, cheap at plugin size, and runs on
    the GUI thread so a change can call straight into the coordinator. The
    ``web/`` tree is Vite's, caches are nobody's, and the project's tests
    are not part of the running plugin.
    """

    def __init__(
        self, root: Path, plugin: str, *, on_change: Callable[[], None]
    ) -> None:
        self._package = Path(root) / plugin
        self._on_change = on_change
        self._seen = self.snapshot()

    def snapshot(self) -> dict[Path, tuple[int, int]]:
        """``{path: (mtime_ns, size)}`` of every watched file right now."""
        seen: dict[Path, tuple[int, int]] = {}
        for path in walk_files(self._package, skip=UNWATCHED, suffix=".py"):
            try:
                stat = path.stat()
            except OSError:  # removed between listing and stat
                continue
            seen[path] = (stat.st_mtime_ns, stat.st_size)
        return seen

    def poll(self) -> bool:
        """Compare with the last snapshot; call ``on_change`` once if it differs."""
        current = self.snapshot()
        if current == self._seen:
            return False
        self._seen = current
        self._on_change()
        return True

    def resync(self) -> None:
        """Take the current tree as the baseline, forgetting edits made meanwhile."""
        self._seen = self.snapshot()
