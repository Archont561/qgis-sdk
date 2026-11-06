"""The project as a page and a plugin handler see it (TASK-88).

A QGIS project is three things at once: a CRS, a bag of variables and custom
properties, and a *tree* of layers and groups where order and visibility are
part of the answer. decision-54 point 3 gives each of those a place here, and
four choices are deliberate.

*The tree crosses flat, not nested.* A recursive JSON schema has no finite
TypeScript type, and the generator refuses one rather than inventing ``any``. So
:class:`LayerTree` is a **pre-order** list of :class:`LayerNode` values, each
naming its ``parent`` group id (``None`` for the root's own children). Order is
the list's order, nesting is the ``parent`` field, and ``children_of`` rebuilds
the nested view a UI wants. A group and a layer are one node type with a
``kind``, because both are things a tree lists.

*Names are not identities.* A group has an id of its own, so a group and a layer
may share a name without :meth:`LayerTree.children_of` guessing which was meant.

*Variables and custom properties are key/value entries, never a free-form map.*
A map has no declared shape to generate a type from, and a pair of lists
preserves the order QGIS reports; :class:`ProjectEntry` is the one type both use.

*A change is a kind, not a diff.* :class:`ProjectChange` says *what* moved
(``crs``, ``layers``, ``tree``, ``variables``, ``properties``, ``bookmarks``) and
which layer ids a view should re-read. A diff would have to describe every kind
of edit and would still be incomplete; "re-read this" is the contract a page can
honour, and the frames arrive in the order the project produced them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from qgis_sdk.models.canvas import CANVAS_EXTENT, CanvasExtent

__all__ = [
    "BOOKMARK",
    "LAYER_NODE",
    "LAYER_TREE",
    "PROJECT_CHANGE",
    "PROJECT_CHANGE_KINDS",
    "PROJECT_ENTRY",
    "PROJECT_FILE",
    "Bookmark",
    "LayerNode",
    "LayerTree",
    "NodeKind",
    "ProjectChange",
    "ProjectEntry",
    "ProjectFile",
]

#: What a change frame says moved. Spelled as the service's own areas, so a page
#: maps a kind to the call it re-issues without a second vocabulary.
PROJECT_CHANGE_KINDS: tuple[str, ...] = (
    "crs",
    "layers",
    "tree",
    "variables",
    "properties",
    "bookmarks",
)

NodeKind = Literal["layer", "group"]


@dataclass(frozen=True, slots=True)
class LayerNode:
    """One node of the project tree: a layer, or a group holding more nodes.

    ``parent`` is the group id the node sits in, or ``None`` for a node the root
    holds. ``visible`` is the node's own visibility, which is what the user
    toggled - a node inside a hidden group is still ``visible``.
    """

    id: str
    name: str
    kind: NodeKind
    visible: bool = True
    parent: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("layer", "group"):
            raise ValueError(f"kind is layer or group, not {self.kind!r}")
        for name in ("id", "name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} is a nonempty string")
        if self.parent is not None and (
            not isinstance(self.parent, str) or not self.parent
        ):
            raise ValueError("parent is a nonempty group id or None")
        if self.parent == self.id:
            raise ValueError(f"node {self.id!r} cannot be its own parent")

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "visible": self.visible,
            "parent": self.parent,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> LayerNode:
        unknown = set(value) - {"id", "name", "kind", "visible", "parent"}
        if unknown:
            raise ValueError(f"a LayerNode has no field {min(unknown)!r}")
        return cls(
            id=value["id"],
            name=value["name"],
            kind=value["kind"],
            visible=bool(value.get("visible", True)),
            parent=value.get("parent"),
        )


@dataclass(frozen=True, slots=True)
class LayerTree:
    """The project tree as a pre-order list of nodes.

    Every node appears once, after its parent. A group a node names must exist
    in the same tree as a group, so a tree cannot describe a dangling branch -
    the one invariant a reader of ``parent`` depends on.
    """

    nodes: tuple[LayerNode, ...] = ()

    def __post_init__(self) -> None:
        seen: dict[str, LayerNode] = {}
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"node {node.id!r} is listed twice")
            if node.parent is not None:
                parent = seen.get(node.parent)
                if parent is None:
                    raise ValueError(
                        f"node {node.id!r} names parent {node.parent!r}, which is "
                        "not a group above it in the tree"
                    )
                if parent.kind != "group":
                    raise ValueError(
                        f"node {node.id!r} sits in {node.parent!r}, which is a layer"
                    )
            seen[node.id] = node

    def __len__(self) -> int:
        return len(self.nodes)

    def node(self, node_id: str) -> LayerNode:
        """Return one node by id."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def children_of(self, parent: str | None = None) -> tuple[LayerNode, ...]:
        """Return the nodes directly inside ``parent`` (``None`` = the root)."""
        return tuple(node for node in self.nodes if node.parent == parent)

    def layer_ids(self) -> tuple[str, ...]:
        """Return every layer id in tree order."""
        return tuple(node.id for node in self.nodes if node.kind == "layer")

    def group_ids(self) -> tuple[str, ...]:
        """Return every group id in tree order."""
        return tuple(node.id for node in self.nodes if node.kind == "group")

    def to_wire(self) -> dict[str, Any]:
        return {"nodes": [node.to_wire() for node in self.nodes]}

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> LayerTree:
        unknown = set(value) - {"nodes"}
        if unknown:
            raise ValueError(f"a LayerTree has no field {min(unknown)!r}")
        return cls(nodes=tuple(LayerNode.from_wire(item) for item in value["nodes"]))


@dataclass(frozen=True, slots=True)
class ProjectEntry:
    """One variable or custom property: a name and its string value."""

    key: str
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("a project entry has a nonempty key")
        if not isinstance(self.value, str):
            raise TypeError("a project entry's value is a string")

    def to_wire(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value}

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> ProjectEntry:
        unknown = set(value) - {"key", "value"}
        if unknown:
            raise ValueError(f"a ProjectEntry has no field {min(unknown)!r}")
        return cls(key=value["key"], value=value["value"])


@dataclass(frozen=True, slots=True)
class Bookmark:
    """A named extent a user can jump back to."""

    name: str
    extent: CanvasExtent

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("a bookmark has a nonempty name")

    def to_wire(self) -> dict[str, Any]:
        return {"name": self.name, "extent": self.extent.to_wire()}

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> Bookmark:
        unknown = set(value) - {"name", "extent"}
        if unknown:
            raise ValueError(f"a Bookmark has no field {min(unknown)!r}")
        return cls(name=value["name"], extent=CanvasExtent.from_wire(value["extent"]))


@dataclass(frozen=True, slots=True)
class ProjectFile:
    """A project file that was written, or saved to: its path, as a string."""

    path: str

    def to_wire(self) -> dict[str, Any]:
        return {"path": self.path}


@dataclass(frozen=True, slots=True)
class ProjectChange:
    """One frame of the project change stream: what moved, and which layers.

    ``layer_ids`` is empty when the change was not about layers; a ``tree`` or
    ``layers`` frame carries the ids in tree order so a view can re-read exactly
    the layers it drew before.
    """

    kind: str
    layer_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in PROJECT_CHANGE_KINDS:
            raise ValueError(
                f"kind is one of {', '.join(PROJECT_CHANGE_KINDS)}; not {self.kind!r}"
            )
        for layer_id in self.layer_ids:
            if not isinstance(layer_id, str) or not layer_id:
                raise ValueError("a layer id is a nonempty string")

    def to_wire(self) -> dict[str, Any]:
        return {"kind": self.kind, "layer_ids": list(self.layer_ids)}


def entries(
    pairs: Mapping[str, str] | Sequence[ProjectEntry],
) -> tuple[ProjectEntry, ...]:
    """Normalize a mapping or a sequence of entries into a tuple of entries."""
    if isinstance(pairs, Mapping):
        return tuple(ProjectEntry(key=str(k), value=str(v)) for k, v in pairs.items())
    return tuple(pairs)


# ---------------------------------------------------------------------------
# The wire shapes the generated TypeScript types come from
# ---------------------------------------------------------------------------

LAYER_NODE: dict[str, Any] = {
    "type": "object",
    "title": "LayerNode",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "kind": {"enum": ["layer", "group"]},
        "visible": {"type": "boolean"},
        "parent": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["id", "name", "kind", "visible", "parent"],
    "additionalProperties": False,
}

LAYER_TREE: dict[str, Any] = {
    "type": "object",
    "title": "LayerTree",
    "properties": {"nodes": {"type": "array", "items": LAYER_NODE}},
    "required": ["nodes"],
    "additionalProperties": False,
}

PROJECT_ENTRY: dict[str, Any] = {
    "type": "object",
    "title": "ProjectEntry",
    "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
    "required": ["key", "value"],
    "additionalProperties": False,
}

BOOKMARK: dict[str, Any] = {
    "type": "object",
    "title": "Bookmark",
    "properties": {"name": {"type": "string"}, "extent": CANVAS_EXTENT},
    "required": ["name", "extent"],
    "additionalProperties": False,
}

PROJECT_FILE: dict[str, Any] = {
    "type": "object",
    "title": "ProjectFile",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
    "additionalProperties": False,
}

PROJECT_CHANGE: dict[str, Any] = {
    "type": "object",
    "title": "ProjectChange",
    "properties": {
        "kind": {"enum": list(PROJECT_CHANGE_KINDS)},
        "layer_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["kind"],
    "additionalProperties": False,
}
