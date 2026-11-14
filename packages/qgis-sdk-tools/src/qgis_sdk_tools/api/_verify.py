"""Diff two API inventories: additive, deprecating or breaking, and the version it needs.

decision-56 point 2: `release verify-api` diffs the inventory against the last
release and says what each change costs. The classification is deliberately
small - three answers, each with a consequence - because a gate nobody can
predict is a gate people route around.

* **additive** - a name, rule, operation or command that did not exist. Free in
  a minor.
* **deprecating** - a stable symbol announced for removal; it stays until the
  window closes (see `_removal`).
* **breaking** - a stable symbol removed, or its signature changed. After 1.0 it
  needs a major; before it, a documented minor, which is what `consequence`
  derives from the version being released.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Change",
    "consequence",
    "diff",
    "early_removals",
    "refusals",
    "verdict",
]

ADDITIVE = "additive"
DEPRECATING = "deprecating"
BREAKING = "breaking"

SECTIONS = ("rules", "host_operations", "cli")
DEPRECATIONS = "deprecations"
"""The flat collections: a name either appears or it does not."""


@dataclass(frozen=True, slots=True)
class Change:
    """One difference between two inventories, and what it costs."""

    kind: str
    where: str
    detail: str

    def line(self) -> str:
        """The change as one line a reviewer reads."""
        return f"{self.kind:11} {self.where}: {self.detail}"

    def to_json(self) -> dict[str, str]:
        """The change as a record a workflow can read."""
        return {"kind": self.kind, "where": self.where, "detail": self.detail}


def _flat(old: Sequence[str], new: Sequence[str], section: str) -> list[Change]:
    """Added and removed entries of one flat collection."""
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changes = [Change(ADDITIVE, section, name) for name in added]
    changes += [Change(BREAKING, section, f"removed {name}") for name in removed]
    return changes


def _names(entry: Mapping[str, Any] | None) -> Mapping[str, str]:
    """One module's names, or nothing when the module is new or gone."""
    return {} if entry is None else entry.get("names", {})


def _module(
    name: str, old: Mapping[str, Any] | None, new: Mapping[str, Any] | None
) -> list[Change]:
    """The changes inside one module, judged by the tier the *old* side declared."""
    tier = "stable" if old is None else old.get("tier", "stable")
    before, after = _names(old), _names(new)
    if tier == "internal":
        return []
    changes = [
        Change(ADDITIVE, name, added) for added in sorted(set(after) - set(before))
    ]
    for gone in sorted(set(before) - set(after)):
        changes.append(Change(BREAKING, name, f"removed {gone}"))
    for name_changed in sorted(set(before) & set(after)):
        if before[name_changed] != after[name_changed]:
            changes.append(
                Change(
                    BREAKING,
                    name,
                    f"{name_changed} signature {before[name_changed]} -> {after[name_changed]}",
                )
            )
    return changes


def _key(entry: Mapping[str, str]) -> tuple[str, str]:
    """One deprecation entry's symbol, as a comparable pair."""
    return (entry["module"], entry["name"])


def _deprecating(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[Change]:
    """Names that carry a removal notice now and did not before."""
    marked = {_key(entry) for entry in old.get(DEPRECATIONS, ())}
    return [
        Change(
            DEPRECATING,
            entry["module"],
            f"deprecated {entry['name']} until {entry['removal']}",
        )
        for entry in new.get(DEPRECATIONS, ())
        if _key(entry) not in marked
    ]


def _gone(old: Mapping[str, Any], new: Mapping[str, Any]) -> set[tuple[str, str]]:
    """Every ``(module, name)`` the new document no longer carries."""
    removed: set[tuple[str, str]] = set()
    for module, entry in old.get("modules", {}).items():
        after = new.get("modules", {}).get(module)
        if after is None:
            removed |= {(module, name) for name in entry.get("names", {})}
            continue
        removed |= {(module, name) for name in entry.get("names", {})} - set(
            after.get("names", {})
        )
    return removed


def _order(version: str) -> tuple[int, ...]:
    """A version's numbers, so ``1.10.0`` sorts after ``1.9.0``."""
    release = version.split("-")[0].split("+")[0]
    return tuple(int(piece) if piece.isdigit() else 0 for piece in release.split("."))


def early_removals(
    old: Mapping[str, Any], new: Mapping[str, Any], version: str
) -> list[str]:
    """Removals that land before the version the deprecation announced.

    decision-56 point 3 gives a deprecated symbol a window: no removal earlier
    than the next major after 1.0, or the second following minor before it. The
    mark names that version, so the only question left is whether the release
    being cut has reached it.
    """
    if not version:
        return []
    released, gone = _order(version), _gone(old, new)
    return [
        (
            f"{entry['module']}.{entry['name']} was announced for removal in "
            f"{entry['removal']}, so {version} cannot remove it"
        )
        for entry in old.get(DEPRECATIONS, ())
        if _key(entry) in gone and _order(entry["removal"]) > released
    ]


def diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[Change]:
    """Every change between two inventory documents, in a stable order."""
    before = old.get("modules", {})
    after = new.get("modules", {})
    changes: list[Change] = []
    for name in sorted(set(before) | set(after)):
        changes += _module(name, before.get(name), after.get(name))
    for section in SECTIONS:
        changes += _flat(old.get(section, []), new.get(section, []), section)
    changes += _deprecating(old, new)
    return sorted(
        changes, key=lambda change: (change.where, change.kind, change.detail)
    )


def verdict(changes: Sequence[Change]) -> str:
    """The strongest answer any single change forces, or ``"none"``."""
    for kind in (BREAKING, DEPRECATING, ADDITIVE):
        if any(change.kind == kind for change in changes):
            return kind
    return "none"


def consequence(answer: str, version: str) -> str:
    """What the release must be, given the verdict its changes produced."""
    if answer == BREAKING:
        return (
            f"{version}: a stable symbol changed, so this needs a major after 1.0 "
            "and a documented minor before it (decision-56 point 2)"
        )
    if answer == DEPRECATING:
        return f"{version}: a stable symbol is deprecated, which ships in a minor"
    if answer == ADDITIVE:
        return f"{version}: additive, a minor or patch is enough"
    return f"{version}: no change to the public API"


def _is_major(version: str) -> bool:
    """Whether ``version`` is ``X.0.0``, the shape a breaking change needs."""
    parts = version.split(".")
    return len(parts) == 3 and parts[1:] == ["0", "0"]


def refusals(changes: Sequence[Change], version: str) -> list[str]:
    """The reasons this release cannot carry these changes at ``version``.

    Before 1.0 every number is a documented minor away, so nothing is refused.
    After 1.0 a breaking change needs a major, and shipping it as anything else
    is how a promise stops meaning anything.
    """
    if verdict(changes) != BREAKING or version.split(".")[0] == "0":
        return []
    if _is_major(version):
        return []
    broken = sum(1 for change in changes if change.kind == BREAKING)
    reason = f"{broken} stable change(s) cannot ship as {version}; "
    return [reason + consequence(BREAKING, version)]
