from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis.core import (
    QgsBookmark,
    QgsProject,
    QgsReferencedRectangle,
)

from qgis_sdk.adapters.qgis.layers import NativeLayers
from qgis_sdk.adapters.qgis.rasters import NativeRasters
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    Bookmark,
    CanvasExtent,
    LayerNode,
    LayerTree,
    ProjectChange,
    ProjectEntry,
    ProjectFile,
    QgisSdkBookmarkNotFoundError,
    QgisSdkLayerNotFoundError,
    QgisSdkProjectFileError,
)
from qgis_sdk.services import ProjectChanged, ProjectWatchCanceller

from ._connect_state import (
    PROPERTY_SCOPE,
    CcReturn,
    CcState,
    NativeProjectMixin1,
    cc_connect_p1,
    cc_connect_p2,
    cc_connect_p3,
    cc_connect_p4,
    write_facts1,
)
from ._helpers import bookmark_list, box, extent, group_id_of, is_layer

if TYPE_CHECKING:
    from qgis.core import QgsLayerTreeGroup


class _NativeProjectMixin2:
    def unset_custom_property(self, name: str) -> tuple[ProjectEntry, ...]:
        """Remove one custom property; an absent name is a no-op."""
        self._scope.ensure_open()
        if name in self._property_keys():
            with self._editing():
                self._project.removeEntry(PROPERTY_SCOPE, name)
            self._notify("properties")
        return self.custom_properties()

    def _property_value(self, key: str) -> str:
        """Return one stored value, whichever shape the reader answers.

        ``readEntry`` returns the value itself on one build and a
        ``(value, found)`` pair on the next, so the pair is unwrapped rather than
        a string that spells both being handed to a page.
        """
        stored = self._project.readEntry(PROPERTY_SCOPE, key)
        if isinstance(stored, tuple | list) and len(stored) == 2:
            stored = stored[0]
        return str(stored)

    def _property_keys(self) -> tuple[str, ...]:
        """Return the scoped keys, without the scope prefix the project stores.

        ``entryList`` answers the full path it stored (``qgis-sdk/author``) on
        some builds and the bare key on others, so the prefix is stripped when
        it is there and left alone when it is not.
        """
        prefix = f"{PROPERTY_SCOPE}/"
        return tuple(
            key.removeprefix(prefix)
            for key in (str(raw) for raw in self._project.entryList(PROPERTY_SCOPE, ""))
        )

    # -- bookmarks ----------------------------------------------------------

    def bookmarks(self) -> tuple[Bookmark, ...]:
        """Return the project's bookmarked extents, in the host's order."""
        self._scope.ensure_open()
        return tuple(
            Bookmark(name, extent(rectangle)) for name, rectangle in self._bookmarks()
        )

    def bookmark(self, name: str) -> Bookmark:
        """Return one bookmark by name."""
        self._scope.ensure_open()
        for bookmark_name, rectangle in self._bookmarks():
            if bookmark_name == name:
                return Bookmark(name, extent(rectangle))
        raise QgisSdkBookmarkNotFoundError(name)

    def add_bookmark(self, name: str, extent: CanvasExtent) -> tuple[Bookmark, ...]:
        """Add a bookmark, replacing one of the same name."""
        self._scope.ensure_open()
        boxes = [
            (existing, box) for existing, box in self._bookmarks() if existing != name
        ]
        boxes.append((name, extent))
        self._replace_bookmarks(boxes)
        self._notify("bookmarks")
        return self.bookmarks()

    def remove_bookmark(self, name: str) -> tuple[Bookmark, ...]:
        """Remove one bookmark by name."""
        self._scope.ensure_open()
        boxes = [
            (existing, box) for existing, box in self._bookmarks() if existing != name
        ]
        if len(boxes) == len(self._bookmarks()):
            raise QgisSdkBookmarkNotFoundError(name)
        self._replace_bookmarks(boxes)
        self._notify("bookmarks")
        return self.bookmarks()

    # -- file ---------------------------------------------------------------

    def read(self, source: Path) -> LayerTree:
        """Replace the open project with the one in ``source``."""
        self._scope.ensure_open()
        source = Path(source)
        with self._editing():
            read = self._project.read(str(source))
        if not read:
            raise QgisSdkProjectFileError(str(source), "QGIS could not read this file")
        self._notify("tree", self.layer_ids())
        return self.layer_tree()

    def write(self, destination: Path, *, overwrite: bool = False) -> ProjectFile:
        """Write the project to ``destination``, staging a partial file first."""
        self._scope.ensure_open()
        destination = Path(destination)
        if destination.suffix != ".qgs":
            raise QgisSdkProjectFileError(
                str(destination), "a project file ends in .qgs"
            )
        if destination.exists() and not overwrite:
            raise QgisSdkProjectFileError(
                str(destination), "the file exists; write with overwrite to replace it"
            )
        if not destination.parent.is_dir():
            raise QgisSdkProjectFileError(
                str(destination), "the destination's directory does not exist"
            )
        partial = destination.with_name(f".{destination.name}.partial")
        try:
            written = self._project.write(str(partial))
        except OSError as error:
            raise QgisSdkProjectFileError(str(destination), str(error)) from error
        if not written:
            raise QgisSdkProjectFileError(
                str(destination), "QGIS could not write this project"
            )
        return write_facts1(destination, partial)

    def save(self) -> ProjectFile:
        """Save to the file the project was opened from."""
        self._scope.ensure_open()
        filename = self._project.fileName()
        if not filename:
            raise QgisSdkProjectFileError(
                "", "the project has no file yet; write it to a path first"
            )
        if not self._project.write():
            raise QgisSdkProjectFileError(filename, "QGIS could not save this project")
        return ProjectFile(path=str(filename))

    # -- changes ------------------------------------------------------------

    def watch_changes(self, on_change: ProjectChanged) -> ProjectWatchCanceller:
        """Call ``on_change`` whenever the project changes, until cancelled."""
        self._scope.ensure_open()
        self._listeners.append(on_change)
        self._connect()

        def cancel() -> None:
            if on_change in self._listeners:
                self._listeners.remove(on_change)

        return cancel

    def _connect(self) -> None:
        """Hook QGIS's own signals once, mapping each to the kind it means."""
        _s = CcState(self=self)
        for _p in (cc_connect_p1, cc_connect_p2, cc_connect_p3, cc_connect_p4):
            _r = _p(_s)
            if isinstance(_r, CcReturn):
                return _r.value
        return None

    @staticmethod
    def _connect_signal(source: Any, name: str, handler: Any) -> bool:
        """Connect ``handler`` to ``source.name`` when that member is a signal."""
        connect = getattr(getattr(source, name, None), "connect", None)
        if connect is None:
            return False
        connect(handler)
        return True


class _NativeProjectMixin3:
    @contextmanager
    def _editing(self) -> Iterator[None]:
        """Ignore QGIS's own signals while the service performs one edit.

        QGIS emits ``crsChanged``, ``layerWasAdded`` and friends for changes this
        service makes too. The service emits one frame per call itself, so the
        echo inside the call is dropped: one change, one frame, in order.
        """
        self._busy += 1
        try:
            yield
        finally:
            self._busy -= 1

    def _notify(
        self, kind: str, layer_ids: tuple[str, ...] = (), *, from_signal: bool = False
    ) -> None:
        """Deliver one frame to every listener, in order."""
        if not self._listeners:
            return
        if from_signal and self._busy:
            return
        frame = ProjectChange(kind=kind, layer_ids=layer_ids)
        for listener in tuple(self._listeners):
            listener(frame)

    # -- native helpers -----------------------------------------------------

    def _root(self) -> QgsLayerTreeGroup:
        return self._project.layerTreeRoot()

    def _walk(
        self, group: QgsLayerTreeGroup, parent: str | None, nodes: list[LayerNode]
    ) -> None:
        """Append ``group``'s children in document order, recursing into groups."""
        for child in group.children():
            if is_layer(child):
                nodes.append(
                    LayerNode(
                        id=child.layerId(),
                        name=child.name(),
                        kind="layer",
                        visible=child.itemVisibilityChecked(),
                        parent=parent,
                    )
                )
                continue
            node = LayerNode(
                id=group_id_of(child),
                name=child.name(),
                kind="group",
                visible=child.itemVisibilityChecked(),
                parent=parent,
            )
            nodes.append(node)
            self._walk(child, node.id, nodes)

    def _group(self, group: str) -> QgsLayerTreeGroup:
        """Return the group whose derived id is ``group``.

        The walk is this module's own rather than ``findGroups()``: the id a
        caller holds came from :meth:`_walk`, so the lookup that resolves it has
        to derive it the same way, and a build whose ``findGroups`` stops at the
        first level must not make a nested group unreachable.
        """
        pending = [self._root()]
        while pending:
            for child in pending.pop().children():
                if is_layer(child):
                    continue
                if group_id_of(child) == group:
                    return child
                pending.append(child)
        raise QgisSdkLayerNotFoundError(group)

    def _group_or_root(self, group: str | None) -> Any:
        return self._root() if group is None else self._group(group)

    def _qgs_map_layer(self, layer_id: str) -> Any:
        """The native handle of an owned layer, of either kind.

        Package handoff: the project must add the very instance the layers or
        rasters adapter owns, so this sibling call is deliberate and documented
        on those adapters' ``_qgs_*`` methods.
        """
        if self._rasters is not None and self._rasters.knows(layer_id):
            return self._rasters._qgs_raster(layer_id)
        return self._layers._qgs_layer(layer_id)

    def _bookmarks(self) -> list[tuple[str, Any]]:
        """Return ``(name, extent)`` pairs, in the manager's order."""
        manager = self._project.bookmarkManager()
        return [(str(b.name()), b.extent()) for b in bookmark_list(manager)]

    def _replace_bookmarks(self, boxes: list[tuple[str, CanvasExtent]]) -> None:
        """Rewrite the manager so it holds exactly ``boxes``, names and order kept."""
        manager = self._project.bookmarkManager()
        for bookmark in bookmark_list(manager):
            manager.removeBookmark(bookmark.id())
        crs = self._project.crs()
        for name, canvas_extent in boxes:
            rectangle = QgsReferencedRectangle(box(canvas_extent), crs)
            try:
                manager.addBookmark(rectangle, name)
            except TypeError:
                # The other spelling of the same call: a bookmark object that
                # carries its own name, which is all this build accepts.
                bookmark = QgsBookmark()
                bookmark.setName(name)
                bookmark.setExtent(rectangle)
                manager.addBookmark(bookmark)

    def _release(self) -> None:
        """Drop the listeners; the project itself belongs to the application."""
        self._listeners.clear()


class NativeProject(NativeProjectMixin1, _NativeProjectMixin2, _NativeProjectMixin3):
    """Edit the application's ``QgsProject`` and read it back."""

    def __init__(
        self,
        layers: NativeLayers,
        scope: ResourceScope,
        project: QgsProject | None = None,
        *,
        rasters: NativeRasters | None = None,
    ) -> None:
        self._layers = layers
        self._scope = scope
        self._project = project if project is not None else QgsProject.instance()
        self._rasters = rasters
        self._listeners: list[ProjectChanged] = []
        self._connected = False
        #: Depth of service calls in progress. QGIS emits its own signal for
        #: edits this service makes, so the signal is ignored while a call runs
        #: and the call emits exactly one frame itself - one change, one frame.
        self._busy = 0
        scope.on_close(self._release)
