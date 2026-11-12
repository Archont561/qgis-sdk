"""The reloader's vocabulary: the host protocol, the report, the constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Protocol

from qgis_sdk.core import QuiesceOutcome

__all__ = [
    "ADVISORY_RULES",
    "DEBOUNCE_MS",
    "PROJECT_RULES",
    "QUIESCE_SECONDS",
    "UNWATCHED",
    "WATCH_INTERVAL_MS",
    "NotifyLevel",
    "Outcome",
    "PluginHost",
    "ReloadReport",
]

Outcome = Literal["reloaded", "refused", "disabled", "coalesced"]
NotifyLevel = Literal["info", "warning", "critical"]

#: How long a revision gets to reach a safe point before the reload is refused.
QUIESCE_SECONDS: Final = 2.0
#: Bursts of edits within this window become one reload.
DEBOUNCE_MS: Final = 300
#: How often the source watcher compares the tree.
WATCH_INTERVAL_MS: Final = 500
#: Findings of these rules only warn: the revision would still run.
ADVISORY_RULES: Final = frozenset({"QGIS001", "ARCH001"})
#: Directories under the plugin package the watcher never looks into.
UNWATCHED: Final = frozenset({"web", "__pycache__", "node_modules"})

#: Rule families raised on ``pyproject.toml`` that still concern the plugin:
#: the host package is rendered from them (decision-43).
PROJECT_RULES: Final = ("PROJECT", "CONFIG", "META", "GRANT", "VERSION")


class PluginHost(Protocol):
    """What the coordinator needs from ``qgis.utils``; faked in tests."""

    def available(self, name: str) -> bool: ...  # QGIS can see the package
    def load(self, name: str) -> bool: ...  # import it
    def start(self, name: str) -> bool: ...  # classFactory + initGui
    def unload(self, name: str) -> bool: ...  # unload + drop its modules
    def forget(self, name: str) -> None: ...  # drop modules after a failed load
    def running(self, name: str) -> bool: ...  # in active_plugins
    def quiesce(self, name: str) -> QuiesceOutcome: ...  # PluginRuntime.quiesce
    def resume(self, name: str) -> None: ...  # PluginRuntime.resume


@dataclass(frozen=True, slots=True)
class ReloadReport:
    """What one reload attempt did; the exercise writes these out."""

    generation: int
    outcome: Outcome
    revision: int
    running: bool
    problems: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "generation": self.generation,
            "outcome": self.outcome,
            "revision": self.revision,
            "running": self.running,
            "problems": list(self.problems),
            "blockers": list(self.blockers),
            "reason": self.reason,
        }
