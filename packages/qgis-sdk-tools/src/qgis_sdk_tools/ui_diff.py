"""Compare two UI snapshots: what a reader would notice, and what is only pixels.

Decision-51 keeps the JSON canonical so two captures of one surface are
byte-identical. This module answers the next question - *what changed* - with
one rule that matters for tests: a surface whose structure, values or states
changed fails an approved snapshot, and one whose only difference is the PNG
does not, because a screenshot is for humans and agents and a renderer bump is
not a regression.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["Change", "SnapshotDiff", "diff_snapshots", "structural_change"]

#: Surface-level fields a change to which is structural, in reading order.
_SURFACE_FIELDS = ("surface", "kind", "title", "size", "scale", "palette", "findings")

#: Node fields a change to which is structural.
_NODE_FIELDS = ("role", "type", "value", "label", "state", "geometry", "declared")

#: The only field a diff may ignore: the encoded image behind it.
_PIXEL_FIELD = "screenshot"


@dataclass(frozen=True, slots=True)
class Change:
    """One difference at one place: a field, or a whole node appearing."""

    where: str
    field: str
    before: Any
    after: Any

    def render(self) -> str:
        """The line a test failure shows: where, what, and both sides."""
        return f"{self.where}: {self.field} {_show(self.before)} -> {_show(self.after)}"


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    """What differs between two captures, split by whether it can fail a test."""

    changes: tuple[Change, ...] = ()
    pixels: tuple[Change, ...] = ()

    def __bool__(self) -> bool:
        """True when the surfaces differ in anything but the image itself."""
        return bool(self.changes)

    @property
    def identical(self) -> bool:
        """True when nothing differs, not even the screenshot."""
        return not self.changes and not self.pixels

    def render(self, *, limit: int = 20) -> str:
        """A readable report; past ``limit`` lines it says how many were hidden."""
        if self.identical:
            return "no differences"
        lines = [change.render() for change in self.changes]
        if not lines:
            lines = [f"{_PIXEL_FIELD} changed; the structure did not"]
        else:
            lines.extend(change.render() for change in self.pixels)
        if len(lines) > limit:
            hidden = len(lines) - limit
            lines = [*lines[:limit], f"... {hidden} more difference(s)"]
        return "\n".join(lines)


def diff_snapshots(before: Mapping[str, Any], after: Mapping[str, Any]) -> SnapshotDiff:
    """Compare two snapshot trees made by ``surface_snapshot``.

    Structural differences - a field, a node, an order - come back in
    ``changes``; a different screenshot digest comes back in ``pixels``. The
    digest is compared by value, so a capture taken with ``screenshot=False``
    (``None``) against one that has an image is a pixel difference only.
    """
    changes: list[Change] = []
    for name in _SURFACE_FIELDS:
        _compare(
            changes,
            str(before.get("surface", "")),
            name,
            before.get(name),
            after.get(name),
        )
    _diff_nodes(
        changes,
        before.get("nodes") or (),
        after.get("nodes") or (),
        where=str(before.get("surface", "")) or "surface",
    )
    pixels: list[Change] = []
    if before.get(_PIXEL_FIELD) != after.get(_PIXEL_FIELD):
        pixels.append(
            Change(
                where=str(before.get("surface", "")) or "surface",
                field=_PIXEL_FIELD,
                before=before.get(_PIXEL_FIELD),
                after=after.get(_PIXEL_FIELD),
            )
        )
    return SnapshotDiff(changes=tuple(changes), pixels=tuple(pixels))


def structural_change(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """Whether an approval must fail: everything except the image changed."""
    return bool(diff_snapshots(before, after))


def _diff_nodes(
    changes: list[Change],
    before: Sequence[Mapping[str, Any]],
    after: Sequence[Mapping[str, Any]],
    *,
    where: str,
) -> None:
    before_by_id = {_id(node): node for node in before}
    after_by_id = {_id(node): node for node in after}
    for node_id in before_by_id:
        if node_id not in after_by_id:
            changes.append(
                Change(where=node_id, field="node", before="present", after="absent")
            )
    for node_id in after_by_id:
        if node_id not in before_by_id:
            changes.append(
                Change(where=node_id, field="node", before="absent", after="present")
            )
    before_order = [_id(node) for node in before]
    after_order = [_id(node) for node in after]
    if set(before_order) == set(after_order) and before_order != after_order:
        changes.append(
            Change(
                where=where, field="child order", before=before_order, after=after_order
            )
        )
    for node_id, old in before_by_id.items():
        new = after_by_id.get(node_id)
        if new is None:
            continue
        for name in _NODE_FIELDS:
            _compare(changes, node_id, name, old.get(name), new.get(name))
        _diff_nodes(
            changes,
            old.get("children") or (),
            new.get("children") or (),
            where=node_id,
        )


def _compare(
    changes: list[Change], where: str, field: str, before: Any, after: Any
) -> None:
    if before != after:
        changes.append(
            Change(where=where or "surface", field=field, before=before, after=after)
        )


def _id(node: Mapping[str, Any]) -> str:
    return str(node.get("id", "?"))


def _show(value: Any) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)
