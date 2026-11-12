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

from qgis.core import (
    QgsCoordinateReferenceSystem,
)

from qgis_sdk.models import (
    LayerNode,
    LayerTree,
    ProjectEntry,
    ProjectFile,
    QgisSdkLayerNotFoundError,
    QgisSdkProjectFileError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.errors import QgisSdkInvalidRequestError

from ._helpers import group_id_of


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_connect_p1(_s):
    if _s.self._connected:
        return CcReturn(None)
    _s.self._connected = True
    _s.self._connect_signal(
        _s.self._project,
        "crsChanged",
        lambda *_: _s.self._notify("crs", from_signal=True),
    )


def cc_connect_p2(_s):
    _s.self._connect_signal(
        _s.self._project,
        "customVariablesChanged",
        lambda *_: _s.self._notify("variables", from_signal=True),
    )


def cc_connect_p3(_s):
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


def cc_connect_p4(_s):
    for name in ("layerWillBeRemoved", "layersWillBeRemoved", "layerRemoved"):
        _s.name = name
        if _s.self._connect_signal(
            _s.self._project,
            _s.name,
            lambda *_: _s.self._notify("layers", from_signal=True),
        ):
            break


def write_facts1(destination, partial):
    if not partial.is_file():
        raise QgisSdkProjectFileError(str(destination), "the writer produced no file")
    partial.replace(destination)
    return ProjectFile(path=str(destination))


GROUP_ID_PREFIX = "group:"
PROPERTY_SCOPE = "qgis-sdk"


class NativeProjectMixin1:
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
        # ``group_id_of`` answers "" for the root, so compare against ``group``
        # spelled the same way: a layer already at the root is already placed.
        if existing is not None and group_id_of(existing.parent()) == (group or ""):
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
