"""PyQGIS-backed project service: CRS, entries, bookmarks, tree and file.

Adding a layer is a separate, explicit step from producing one: decision-19 adds
an output to the project only after the operation succeeded, so this adapter
never adds anything on its own.

The tree is read and edited through ``QgsProject.instance().layerTreeRoot()`` and
crosses as the flat, pre-order
:class:`~qgis_sdk.models.project.LayerTree` a page can draw. A *group* has no id
of its own in QGIS, so one is derived from its position - ``group:Elevation`` for
a root group, ``group:Elevation/Detail`` for a nested one - which is stable for as
long as the group keeps its name and its parent's name. Two sibling groups with
one name are the one ambiguity such an id cannot resolve, and they are the same
ambiguity ``findGroup`` by name has; a project needs the distinct names QGIS's own
group dialog asks for.

Bookmarks are project-level extents, stored with the project's CRS, and variables
and custom properties are one key/value model on both sides, so
:class:`~qgis_sdk.models.project.ProjectEntry` covers both.

Writes are staged: :meth:`write` validates the destination, writes a partial file
beside it and replaces the destination only when the writer succeeded, so a
failed save leaves the previous project file intact.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis.core import (
    QgsBookmark,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsRectangle,
    QgsReferencedRectangle,
)

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
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.errors import QgisSdkInvalidRequestError
from qgis_sdk.services import ProjectChanged, ProjectWatchCanceller

from .layers import NativeLayers
from .rasters import NativeRasters


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_connect_p1(_s):
    if _s.self._connected:
        return _CcReturn(None)
    _s.self._connected = True
    _s.self._connect_signal(
        _s.self._project,
        "crsChanged",
        lambda *_: _s.self._notify("crs", from_signal=True),
    )


def _cc_connect_p2(_s):
    _s.self._connect_signal(
        _s.self._project,
        "customVariablesChanged",
        lambda *_: _s.self._notify("variables", from_signal=True),
    )


def _cc_connect_p3(_s):
    # QGIS reports a layer entering or leaving the project on the project
    # itself (``layerWasAdded``/``layerWillBeRemoved``); the registry
    # bridge's own pair is spelled differently from one build to the next.
    for name in ("layerWasAdded", "layersAdded", "layerAdded"):
        _s.name = name
        if _s.self._connect_signal(
            _s.self._project,
            _s.name,
            lambda *_: _s.self._notify("layers", from_signal=True),
        ):
            break


def _cc_connect_p4(_s):
    for name in ("layerWillBeRemoved", "layersWillBeRemoved", "layerRemoved"):
        _s.name = name
        if _s.self._connect_signal(
            _s.self._project,
            _s.name,
            lambda *_: _s.self._notify("layers", from_signal=True),
        ):
            break


def _write_facts1(destination, partial):
    if not partial.is_file():
        raise QgisSdkProjectFileError(str(destination), "the writer produced no file")
    partial.replace(destination)
    return ProjectFile(path=str(destination))


if TYPE_CHECKING:  # pragma: no cover - typing only
    from qgis.core import QgsLayerTreeGroup, QgsLayerTreeNode

__all__ = ["GROUP_ID_PREFIX", "NativeProject"]

#: Group ids are derived paths, not QGIS values; the prefix keeps them from
#: colliding with the layer id of a layer that happens to share the name.
GROUP_ID_PREFIX = "group:"

#: The project scope custom properties are stored under. ``QgsProject`` keeps
#: them as scoped entries, which is the one spelling a 3.x and a 4.x build share.
PROPERTY_SCOPE = "qgis-sdk"


class _NativeProjectMixin1:
    # -- membership and tree ------------------------------------------------

    def layer_ids(self) -> tuple[str, ...]:
        """Return the project's layer ids in tree order."""
        self._scope.ensure_open()
        return tuple(
            node.id for node in self.layer_tree().nodes if node.kind == "layer"
        )

    def add_layer(self, layer_id: str, *, group: str | None = None) -> LayerTree:
        """Add an owned layer to the project, optionally into a group."""
        self._scope.ensure_open()
        layer = self._qgs_map_layer(layer_id)
        target = self._group_or_root(group)
        existing = self._root().findLayer(layer_id)
        # ``_group_id_of`` answers "" for the root, so compare against ``group``
        # spelled the same way: a layer already at the root is already placed.
        if existing is not None and _group_id_of(existing.parent()) == (group or ""):
            return self.layer_tree()
        with self._editing():
            if existing is not None:
                clone = existing.clone()
                existing.parent().removeChildNode(existing)
                target.addChildNode(clone)
            else:
                # Register with the project, but leave the placement to the
                # tree: ``addMapLayer`` alone would put it at the root.
                self._project.addMapLayer(layer, False)
                target.addLayer(layer)
        self._notify("layers", (layer_id,))
        return self.layer_tree()

    def remove_layer(self, layer_id: str) -> LayerTree:
        """Remove one layer from the project; the layer itself stays open."""
        self._scope.ensure_open()
        node = self._root().findLayer(layer_id)
        if node is None:
            raise QgisSdkLayerNotFoundError(layer_id)
        with self._editing():
            node.parent().removeChildNode(node)
        self._notify("layers", (layer_id,))
        return self.layer_tree()

    def move_layer(
        self, layer_id: str, *, group: str | None = None, index: int | None = None
    ) -> LayerTree:
        """Move one layer into ``group``, at ``index`` among that group's children."""
        self._scope.ensure_open()
        node = self._root().findLayer(layer_id)
        if node is None:
            raise QgisSdkLayerNotFoundError(layer_id)
        target = self._group_or_root(group)
        siblings = len(target.children())
        if index is not None and index > siblings:
            raise QgisSdkInvalidRequestError(
                f"index {index} is past the end of "
                f"{group or 'the root'} ({siblings} children)"
            )
        with self._editing():
            clone = node.clone()
            node.parent().removeChildNode(node)
            target.insertChildNode(
                len(target.children()) if index is None else index, clone
            )
        self._notify("tree", (layer_id,))
        return self.layer_tree()

    def set_visible(self, node_id: str, visible: bool) -> LayerTree:
        """Show or hide one node, and answer the tree it produced."""
        self._scope.ensure_open()
        node = self._root().findLayer(node_id)
        if node is None:
            node = self._group(node_id)
        node.setItemVisibilityChecked(bool(visible))
        self._notify("tree")
        return self.layer_tree()

    def layer_tree(self) -> LayerTree:
        """Return the whole tree as a flat pre-order list."""
        self._scope.ensure_open()
        nodes: list[LayerNode] = []
        self._walk(self._root(), None, nodes)
        return LayerTree(nodes=tuple(nodes))

    # -- CRS ----------------------------------------------------------------

    def crs(self) -> str | None:
        """Return the project's CRS authority id, or ``None`` when unset."""
        self._scope.ensure_open()
        return self._project.crs().authid() or None

    def set_crs(self, auth_id: str) -> str:
        """Set the project's CRS to a resolvable authority id."""
        self._scope.ensure_open()
        crs = QgsCoordinateReferenceSystem(auth_id)
        if not crs.isValid():
            raise QgisSdkUnsupportedCapabilityError(
                "crs", f"{auth_id!r} is not a CRS this host can resolve"
            )
        with self._editing():
            self._project.setCrs(crs)
        self._notify("crs")
        # A CRS built from WKT may have no authority id; then the identifier the
        # caller named is the honest answer, and it is what a re-read would see.
        return crs.authid() or str(auth_id)

    # -- variables and properties -------------------------------------------

    def variables(self) -> tuple[ProjectEntry, ...]:
        """Return the project's expression variables."""
        self._scope.ensure_open()
        values = self._project.customVariables()
        return tuple(
            ProjectEntry(str(key), str(value)) for key, value in values.items()
        )

    def set_variable(self, name: str, value: str) -> tuple[ProjectEntry, ...]:
        """Set one project variable and answer the list it produced."""
        self._scope.ensure_open()
        variables = dict(self._project.customVariables())
        variables[name] = value
        with self._editing():
            self._project.setCustomVariables(variables)
        self._notify("variables")
        return self.variables()

    def unset_variable(self, name: str) -> tuple[ProjectEntry, ...]:
        """Remove one project variable; an absent name is a no-op."""
        self._scope.ensure_open()
        variables = dict(self._project.customVariables())
        if variables.pop(name, None) is not None:
            with self._editing():
                self._project.setCustomVariables(variables)
            self._notify("variables")
        return self.variables()

    def custom_properties(self) -> tuple[ProjectEntry, ...]:
        """Return the project's custom properties."""
        self._scope.ensure_open()
        return tuple(
            ProjectEntry(key, self._property_value(key))
            for key in self._property_keys()
        )

    def set_custom_property(self, name: str, value: str) -> tuple[ProjectEntry, ...]:
        """Set one custom property and answer the list it produced."""
        self._scope.ensure_open()
        with self._editing():
            self._project.writeEntry(PROPERTY_SCOPE, name, value)
        self._notify("properties")
        return self.custom_properties()


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
        return tuple(Bookmark(name, _extent(box)) for name, box in self._bookmarks())

    def bookmark(self, name: str) -> Bookmark:
        """Return one bookmark by name."""
        self._scope.ensure_open()
        for bookmark_name, box in self._bookmarks():
            if bookmark_name == name:
                return Bookmark(name, _extent(box))
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
        return _write_facts1(destination, partial)

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
        _s = _CcState(self=self)
        for _p in (_cc_connect_p1, _cc_connect_p2, _cc_connect_p3, _cc_connect_p4):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
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
            if _is_layer(child):
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
                id=_group_id_of(child),
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
                if _is_layer(child):
                    continue
                if _group_id_of(child) == group:
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
        return [(str(b.name()), b.extent()) for b in _bookmark_list(manager)]

    def _replace_bookmarks(self, boxes: list[tuple[str, CanvasExtent]]) -> None:
        """Rewrite the manager so it holds exactly ``boxes``, names and order kept."""
        manager = self._project.bookmarkManager()
        for bookmark in _bookmark_list(manager):
            manager.removeBookmark(bookmark.id())
        crs = self._project.crs()
        for name, extent in boxes:
            rectangle = QgsReferencedRectangle(_box(extent), crs)
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


class NativeProject(_NativeProjectMixin1, _NativeProjectMixin2, _NativeProjectMixin3):
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


def _is_layer(node: QgsLayerTreeNode) -> bool:
    """Whether a tree node is a layer rather than a group.

    A layer node answers ``layerId()`` and a group does not, which is the one
    difference both spellings of the tree classes agree on.
    """
    return hasattr(node, "layerId")


def _group_id_of(node: Any) -> str:
    """Return the derived id of ``node`` and its ancestors, or ``""`` for the root."""
    names: list[str] = []
    current = node
    while current is not None and not _is_layer(current):
        parent = current.parent()
        if parent is None:
            break
        names.append(str(current.name()))
        current = parent
    if not names:
        return ""
    return GROUP_ID_PREFIX + "/".join(reversed(names))


def _bookmark_list(manager: Any) -> list[Any]:
    """Return the manager's bookmarks as a list.

    ``QgsBookmarkManager.bookmarks()`` answers a name-keyed map on a 3.x build
    and a plain list on a 4.x one, so the callers index neither.
    """
    bookmarks = manager.bookmarks()
    values = getattr(bookmarks, "values", None)
    return list(bookmarks if values is None else values())


def _extent(box: Any) -> CanvasExtent:
    return CanvasExtent(
        x_min=box.xMinimum(),
        y_min=box.yMinimum(),
        x_max=box.xMaximum(),
        y_max=box.yMaximum(),
        crs=None,
    )


def _box(extent: CanvasExtent) -> QgsRectangle:
    return QgsRectangle(extent.x_min, extent.y_min, extent.x_max, extent.y_max)
