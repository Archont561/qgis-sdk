"""An in-memory ``Project``: a CRS, entries, bookmarks, a tree and a file.

:class:`FakeProject` stores exactly what the contract observes - the tree's
nodes in order, the two entry lists, the bookmarks, the project file path and the
change frames it emitted - and derives everything else, so a test never has to
keep two representations in step.

Its file format is JSON, written and read by this class alone. That is a fake's
freedom and its boundary: the native adapter writes a real ``.qgs`` and can read
a project QGIS saved, while this one round-trips only its own document. Both are
held to the same contract, and the round-trip test declares a project through
this module on both backends precisely so the format is not what is under test -
the tree model is.

Groups are created by :meth:`set_tree` (the setup path, standing in for a project
opened from a file); the service edits a tree that already exists, which is why
there is no ``add_group`` on the Protocol.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
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
    QgisSdkBookmarkNotFoundError,
    QgisSdkLayerNotFoundError,
    QgisSdkProjectFileError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.errors import QgisSdkInvalidRequestError
from qgis_sdk.services import Layers, ProjectChanged, ProjectWatchCanceller


def _read_facts11234567891011121314151617(**values):
    return _read_facts112345678910111213141516(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345678910111213141516(**values):
    return _read_facts1123456789101112131415(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123456789101112131415(**values):
    return _read_facts11234567891011121314(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11234567891011121314(**values):
    return _read_facts112345678910111213(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345678910111213(**values):
    return _read_facts1123456789101112(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123456789101112(**values):
    return _read_facts11234567891011(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11234567891011(**values):
    return _read_facts112345678910(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345678910(**values):
    return _read_facts1123456789(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123456789(**values):
    return _read_facts112345678(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345678(**values):
    return _read_facts11234567(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11234567(**values):
    return _read_facts1123456(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123456(**values):
    return _read_facts112345(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112345(**values):
    return _read_facts11234(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11234(**values):
    return _read_facts1123(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1123(**values):
    return _read_facts112(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts112(**values):
    return _read_facts11(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts11(**values):
    return _read_facts1(
        bookmarks=values["bookmarks"],
        properties=values["properties"],
        self=values["self"],
        source=values["source"],
        tree=values["tree"],
        variables=values["variables"],
    )


def _read_facts1(**values):
    values["self"]._variables = {
        entry.key: entry.value for entry in values["variables"]
    }
    values["self"]._properties = {
        entry.key: entry.value for entry in values["properties"]
    }
    values["self"]._bookmarks = {
        bookmark.name: bookmark.extent for bookmark in values["bookmarks"]
    }
    values["self"]._path = values["source"]
    values["self"]._changed("tree", layer_ids=values["tree"].layer_ids())
    return values["tree"]


__all__ = ["FakeProject"]

#: The marker every file this fake writes carries, so ``read`` can refuse a
#: document it did not write instead of half-understanding one.
FORMAT = "qgis-sdk-fake-project"
FORMAT_VERSION = 1


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
        """Add an owned layer, or move it when it is already there."""
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
        """Remove one layer from the project; the layer itself stays open."""
        self._scope.ensure_open()
        index = self._require_layer_node(layer_id)
        del self._nodes[index]
        self._changed("layers", layer_ids=(layer_id,))
        return self._tree()

    def move_layer(
        self, layer_id: str, *, group: str | None = None, index: int | None = None
    ) -> LayerTree:
        """Move one layer into ``group`` and to ``index`` among its siblings."""
        self._scope.ensure_open()
        position = self._require_layer_node(layer_id)
        if group is not None:
            self._require_group(group)
        node = self._replace(self._nodes[position], parent=group)
        del self._nodes[position]
        siblings = [
            index_of
            for index_of, other in enumerate(self._nodes)
            if other.parent == group
        ]
        if index is not None and index > len(siblings):
            raise QgisSdkInvalidRequestError(
                f"index {index} is past the end of "
                f"{group or 'the root'} ({len(siblings)} children)"
            )
        if index is None or index == len(siblings):
            insert_at = len(self._nodes)
            if siblings:
                insert_at = siblings[-1] + 1
        else:
            insert_at = siblings[index]
        self._nodes.insert(insert_at, node)
        self._changed("tree", layer_ids=(layer_id,))
        return self._tree()

    def set_visible(self, node_id: str, visible: bool) -> LayerTree:
        """Show or hide one node, and answer the tree it produced."""
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
        """Set the project's CRS; the fake checks only that it looks like one."""
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
        """Set one project variable and answer the list it produced."""
        self._scope.ensure_open()
        self._variables[name] = value
        self._changed("variables")
        return self.variables()

    def unset_variable(self, name: str) -> tuple[ProjectEntry, ...]:
        """Remove one project variable; an absent name is a no-op."""
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
        """Set one custom property and answer the list it produced."""
        self._scope.ensure_open()
        self._properties[name] = value
        self._changed("properties")
        return self.custom_properties()


class _FakeProjectMixin2:
    def unset_custom_property(self, name: str) -> tuple[ProjectEntry, ...]:
        """Remove one custom property; an absent name is a no-op."""
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
        """Return one bookmark by name."""
        self._scope.ensure_open()
        return Bookmark(name, self._require_bookmark(name))

    def add_bookmark(self, name: str, extent: CanvasExtent) -> tuple[Bookmark, ...]:
        """Add a bookmark, replacing one of the same name."""
        self._scope.ensure_open()
        self._bookmarks[name] = extent
        self._changed("bookmarks")
        return self.bookmarks()

    def remove_bookmark(self, name: str) -> tuple[Bookmark, ...]:
        """Remove one bookmark by name."""
        self._scope.ensure_open()
        self._require_bookmark(name)
        del self._bookmarks[name]
        self._changed("bookmarks")
        return self.bookmarks()

    # -- file ---------------------------------------------------------------

    def read(self, source: Path) -> LayerTree:
        """Replace this project with the one in ``source``."""
        self._scope.ensure_open()
        source = Path(source)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except OSError as error:
            raise QgisSdkProjectFileError(str(source), str(error)) from error
        except ValueError as error:
            raise QgisSdkProjectFileError(str(source), f"not JSON: {error}") from error
        if not isinstance(document, Mapping) or document.get("format") != FORMAT:
            raise QgisSdkProjectFileError(
                str(source), "this is not a project this backend can read"
            )
        try:
            tree = LayerTree.from_wire(document["tree"])
            variables = [ProjectEntry.from_wire(item) for item in document["variables"]]
            properties = [
                ProjectEntry.from_wire(item) for item in document["properties"]
            ]
            bookmarks = [Bookmark.from_wire(item) for item in document["bookmarks"]]
        except (KeyError, TypeError, ValueError) as error:
            raise QgisSdkProjectFileError(str(source), str(error)) from error
        self._nodes = list(tree.nodes)
        self._crs = document.get("crs")
        return _read_facts11234567891011121314151617(
            bookmarks=bookmarks,
            properties=properties,
            self=self,
            source=source,
            tree=tree,
            variables=variables,
        )

    def write(self, destination: Path, *, overwrite: bool = False) -> ProjectFile:
        """Write the project document to ``destination``, refusing silently replaced files."""
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
        document = {
            "format": FORMAT,
            "version": FORMAT_VERSION,
            "crs": self._crs,
            "tree": self._tree().to_wire(),
            "variables": [entry.to_wire() for entry in self.variables()],
            "properties": [entry.to_wire() for entry in self.custom_properties()],
            "bookmarks": [bookmark.to_wire() for bookmark in self.bookmarks()],
        }
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
        """Call ``on_change`` for every change, in the order they happened."""
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
        """Declare the tree wholesale; setup, standing in for an opened project."""
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


class _FakeProjectMixin3:
    def _require_layer_node(self, layer_id: str) -> int:
        position = self._index_of(layer_id)
        if position is None or self._nodes[position].kind != "layer":
            raise QgisSdkLayerNotFoundError(layer_id)
        return position

    def _require_group(self, group: str) -> LayerNode:
        position = self._index_of(group)
        if position is None or self._nodes[position].kind != "group":
            raise QgisSdkLayerNotFoundError(group)
        return self._nodes[position]

    def _require_bookmark(self, name: str) -> CanvasExtent:
        try:
            return self._bookmarks[name]
        except KeyError:
            raise QgisSdkBookmarkNotFoundError(name) from None

    @staticmethod
    def _replace(node: LayerNode, **changes: Any) -> LayerNode:
        values: dict[str, Any] = {
            "id": node.id,
            "name": node.name,
            "kind": node.kind,
            "visible": node.visible,
            "parent": node.parent,
        }
        values.update(changes)
        return LayerNode(**values)


class FakeProject(_FakeProjectMixin1, _FakeProjectMixin2, _FakeProjectMixin3):
    """A ``Project`` backend over one in-memory project, with a JSON file."""

    def __init__(self, layers: Layers, scope: ResourceScope) -> None:
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
