from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    Bookmark,
    CanvasExtent,
    LayerNode,
    LayerTree,
    ProjectChange,
    ProjectEntry,
    ProjectFile,
    QgisSdkLayerNotFoundError,
    QgisSdkProjectFileError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.errors import QgisSdkInvalidRequestError
from qgis_sdk.services import Layers, ProjectChanged, ProjectWatchCanceller

from ._fake_project_mixin3 import FakeProjectMixin3
from ._read_state import (
    FORMAT,
    FORMAT_VERSION,
    CcReturn,
    CcState,
    cc_read_p1,
    cc_read_p2,
    cc_read_p3,
)


class _FakeProjectMixin1:
    # -- membership and tree ------------------------------------------------

    def layer_ids(self) -> tuple[str, ...]:
        """Return the project's layer ids in tree order."""
        self._scope.ensure_open()
        return self._tree().layer_ids()

    def layer_tree(self) -> LayerTree:
        """Return the whole tree."""
        self._scope.ensure_open()
        return self._tree()

    def add_layer(self, layer_id: str, *, group: str | None = None) -> LayerTree:
        """Add an owned layer, or move it when it is already there.

        Args:
            layer_id: The layer to add.
            group: The group to add it into, or ``None`` for the root.
        """
        self._scope.ensure_open()
        self._layers.layer(layer_id)
        if group is not None:
            self._require_group(group)
        index = self._index_of(layer_id)
        if index is None:
            node = LayerNode(
                id=layer_id, name=self._layers.layer(layer_id).name, kind="layer"
            )
            self._nodes.append(self._replace(node, parent=group))
        elif group is not None:
            self._nodes[index] = self._replace(self._nodes[index], parent=group)
        self._changed("layers", layer_ids=(layer_id,))
        return self._tree()

    def remove_layer(self, layer_id: str) -> LayerTree:
        """Remove one layer from the project; the layer itself stays open.

        Args:
            layer_id: The layer to remove.
        """
        self._scope.ensure_open()
        index = self._require_layer_node(layer_id)
        del self._nodes[index]
        self._changed("layers", layer_ids=(layer_id,))
        return self._tree()

    def move_layer(
        self, layer_id: str, *, group: str | None = None, index: int | None = None
    ) -> LayerTree:
        """Move one layer into ``group`` and to ``index`` among its siblings.

        Args:
            layer_id: The layer to move.
            group: The group to move it into, or ``None`` for the root.
            index: Where to place it among the group's children.
        """
        self._scope.ensure_open()
        position = self._require_layer_node(layer_id)
        if group is not None:
            self._require_group(group)
        node = self._replace(self._nodes[position], parent=group)
        del self._nodes[position]
        insert_at = _insert_at(self._nodes, group, index)
        self._nodes.insert(insert_at, node)
        self._changed("tree", layer_ids=(layer_id,))
        return self._tree()

    def set_visible(self, node_id: str, visible: bool) -> LayerTree:
        """Show or hide one node, and answer the tree it produced.

        Args:
            node_id: The layer or group to show or hide.
            visible: Whether it is ticked in the tree.
        """
        self._scope.ensure_open()
        for position, node in enumerate(self._nodes):
            if node.id == node_id:
                self._nodes[position] = self._replace(node, visible=visible)
                break
        else:
            raise QgisSdkLayerNotFoundError(node_id)
        self._changed("tree")
        return self._tree()

    # -- CRS ----------------------------------------------------------------

    def crs(self) -> str | None:
        """Return the project's CRS authority id, or ``None`` when unset."""
        self._scope.ensure_open()
        return self._crs

    def set_crs(self, auth_id: str) -> str:
        """Set the project's CRS; the fake checks only that it looks like one.

        Args:
            auth_id: The authority code the project is set to.
        """
        self._scope.ensure_open()
        authority, _, code = auth_id.partition(":")
        if not authority or not code.isdigit():
            raise QgisSdkUnsupportedCapabilityError(
                "crs", f"{auth_id!r} is not an authority id like EPSG:4326"
            )
        self._crs = f"{authority}:{code}"
        self._changed("crs")
        return self._crs

    # -- variables and properties -------------------------------------------

    def variables(self) -> tuple[ProjectEntry, ...]:
        """Return the project's expression variables."""
        self._scope.ensure_open()
        return tuple(ProjectEntry(key, value) for key, value in self._variables.items())

    def set_variable(self, name: str, value: str) -> tuple[ProjectEntry, ...]:
        """Set one project variable and answer the list it produced.

        Args:
            name: The variable name.
            value: The string it holds.
        """
        self._scope.ensure_open()
        self._variables[name] = value
        self._changed("variables")
        return self.variables()

    def unset_variable(self, name: str) -> tuple[ProjectEntry, ...]:
        """Remove one project variable; an absent name is a no-op.

        Args:
            name: The variable to remove.
        """
        self._scope.ensure_open()
        if self._variables.pop(name, None) is not None:
            self._changed("variables")
        return self.variables()

    def custom_properties(self) -> tuple[ProjectEntry, ...]:
        """Return the project's custom properties."""
        self._scope.ensure_open()
        return tuple(
            ProjectEntry(key, value) for key, value in self._properties.items()
        )

    def set_custom_property(self, name: str, value: str) -> tuple[ProjectEntry, ...]:
        """Set one custom property and answer the list it produced.

        Args:
            name: The property name.
            value: The string it holds.
        """
        self._scope.ensure_open()
        self._properties[name] = value
        self._changed("properties")
        return self.custom_properties()


class _FakeProjectMixin2:
    def unset_custom_property(self, name: str) -> tuple[ProjectEntry, ...]:
        """Remove one custom property; an absent name is a no-op.

        Args:
            name: The property to remove.
        """
        self._scope.ensure_open()
        if self._properties.pop(name, None) is not None:
            self._changed("properties")
        return self.custom_properties()

    # -- bookmarks ----------------------------------------------------------

    def bookmarks(self) -> tuple[Bookmark, ...]:
        """Return the project's bookmarks in insertion order."""
        self._scope.ensure_open()
        return tuple(Bookmark(name, extent) for name, extent in self._bookmarks.items())

    def bookmark(self, name: str) -> Bookmark:
        """Return one bookmark by name.

        Args:
            name: The bookmark to read.
        """
        self._scope.ensure_open()
        return Bookmark(name, self._require_bookmark(name))

    def add_bookmark(self, name: str, extent: CanvasExtent) -> tuple[Bookmark, ...]:
        """Add a bookmark, replacing one of the same name.

        Args:
            name: The bookmark's name.
            extent: The box it returns the canvas to.
        """
        self._scope.ensure_open()
        self._bookmarks[name] = extent
        self._changed("bookmarks")
        return self.bookmarks()

    def remove_bookmark(self, name: str) -> tuple[Bookmark, ...]:
        """Remove one bookmark by name.

        Args:
            name: The bookmark to remove.
        """
        self._scope.ensure_open()
        self._require_bookmark(name)
        del self._bookmarks[name]
        self._changed("bookmarks")
        return self.bookmarks()

    # -- file ---------------------------------------------------------------

    def read(self, source: Path) -> LayerTree:
        """Replace this project with the one in ``source``.

        Args:
            source: The project file to read.
        """
        _s = CcState(self=self, source=source)
        for _p in (cc_read_p1, cc_read_p2, cc_read_p3):
            _r = _p(_s)
            if isinstance(_r, CcReturn):
                return _r.value
        return None

    def write(self, destination: Path, *, overwrite: bool = False) -> ProjectFile:
        """Write the project document to ``destination``, refusing silently replaced files.

        Args:
            destination: The file to write.
            overwrite: Whether an existing file may be replaced.
        """
        self._scope.ensure_open()
        destination = Path(destination)
        if destination.suffix != ".qgs":
            raise QgisSdkProjectFileError(
                str(destination), "a project file ends in .qgs"
            )
        if destination.exists() and not overwrite:
            raise QgisSdkProjectFileError(
                str(destination), "the file exists; save with overwrite to replace it"
            )
        document = _document(self)
        try:
            destination.write_text(json.dumps(document, indent=2), encoding="utf-8")
        except OSError as error:
            raise QgisSdkProjectFileError(str(destination), str(error)) from error
        return ProjectFile(path=str(destination))

    def save(self) -> ProjectFile:
        """Save to the file this project was read from or written to."""
        self._scope.ensure_open()
        if self._path is None:
            raise QgisSdkProjectFileError(
                "", "the project has no file yet; write it to a path first"
            )
        return self.write(self._path, overwrite=True)

    # -- changes ------------------------------------------------------------

    def watch_changes(self, on_change: ProjectChanged) -> ProjectWatchCanceller:
        """Call ``on_change`` for every change, in the order they happened.

        Args:
            on_change: What each change frame is handed to.
        """
        self._scope.ensure_open()
        self._listeners.append(on_change)

        def cancel() -> None:
            if on_change in self._listeners:
                self._listeners.remove(on_change)

        return cancel

    def _changed(self, kind: str, *, layer_ids: Sequence[str] = ()) -> None:
        """Record one frame and deliver it to every listener, in order."""
        frame = ProjectChange(kind=kind, layer_ids=tuple(layer_ids))
        self.changes.append(frame)
        for listener in tuple(self._listeners):
            listener(frame)

    # -- tree helpers -------------------------------------------------------

    def set_tree(self, nodes: Sequence[LayerNode]) -> LayerTree:
        """Declare the tree wholesale; setup, standing in for an opened project.

        Args:
            nodes: The nodes the tree is to hold, parents before children.
        """
        self._scope.ensure_open()
        tree = LayerTree(nodes=tuple(nodes))
        self._nodes = list(tree.nodes)
        return tree

    def _tree(self) -> LayerTree:
        return LayerTree(nodes=tuple(self._nodes))

    def _index_of(self, node_id: str) -> int | None:
        for position, node in enumerate(self._nodes):
            if node.id == node_id:
                return position
        return None


def _insert_at(nodes: list[LayerNode], group: str | None, index: int | None) -> int:
    siblings = [
        position for position, other in enumerate(nodes) if other.parent == group
    ]
    if index is not None and index > len(siblings):
        raise QgisSdkInvalidRequestError(
            f"index {index} is past the end of "
            f"{group or 'the root'} ({len(siblings)} children)"
        )
    if index is None or index == len(siblings):
        return siblings[-1] + 1 if siblings else len(nodes)
    return siblings[index]


def _document(project: FakeProject) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "crs": project._crs,
        "tree": project._tree().to_wire(),
        "variables": [entry.to_wire() for entry in project.variables()],
        "properties": [entry.to_wire() for entry in project.custom_properties()],
        "bookmarks": [bookmark.to_wire() for bookmark in project.bookmarks()],
    }


class FakeProject(_FakeProjectMixin1, _FakeProjectMixin2, FakeProjectMixin3):
    """A ``Project`` backend over one in-memory project, with a JSON file."""

    def __init__(self, layers: Layers, scope: ResourceScope) -> None:
        """Build the fake over the layers it reads and one scope.

        Args:
            layers: The layer backend the project's layers are read from.
            scope: The resource scope the fake belongs to.
        """
        self._layers = layers
        self._scope = scope
        self._nodes: list[LayerNode] = []
        self._crs: str | None = None
        self._variables: dict[str, str] = {}
        self._properties: dict[str, str] = {}
        self._bookmarks: dict[str, CanvasExtent] = {}
        self._path: Path | None = None
        self._listeners: list[ProjectChanged] = []
        self.changes: list[ProjectChange] = []
        """Every frame the project emitted, in order - observation, not contract."""
