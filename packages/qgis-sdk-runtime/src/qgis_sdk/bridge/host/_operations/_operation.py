"""The declared operation table, the grants that select from it and the description."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from qgis_sdk.bridge.host._schemas import (
    array,
    page_result,
)
from qgis_sdk.models.layouts import LAYOUT_INFO
from qgis_sdk.models.project import (
    BOOKMARK,
    PROJECT_ENTRY,
)
from qgis_sdk.models.symbology import (
    STYLE_ENTRY,
)

PROJECT_ENTRIES = array(PROJECT_ENTRY)
BOOKMARKS = array(BOOKMARK)
LAYOUTS = page_result(LAYOUT_INFO)
STYLE_ENTRIES = page_result(STYLE_ENTRY)


@dataclass(frozen=True, slots=True)
class HostOperation:
    """One operation of the host surface, declared rather than inferred.

    ``source`` names the Protocol method it wraps so a test can prove the two
    lists stay in step, and ``grant`` is the canonical permission an application
    checks - a namespace-wide flag would grant every future method at once.

    ``destructive`` is the annotation the agent surface reads (decision-27
    point 2, decision-49 point 4): an operation that replaces or discards
    project state - a write, a save, a read over the open project, a removal -
    says so here, so the consent list can ask each time and the audit log can
    mark the call. A read never carries it, and nothing infers it from the
    operation's name.

    ``credential`` is its own annotation, never folded into ``destructive``
    (TASK-92): an operation that authenticates with stored material or reads or
    re-binds the authentication registry says so here. The two axes answer
    different questions - "will this change my project?" and "will this touch
    my credentials?" - and the consent list shows them distinctly, so a read
    that spends a password is not hidden among the writes and a write that
    never authenticates is not dressed up as a credential act.
    """

    id: str
    title: str
    source: str
    grant: str
    affinity: str
    request: Mapping[str, Any]
    result: Mapping[str, Any] | None = None
    events: Mapping[str, Mapping[str, Any]] | None = None
    request_name: str | None = None
    result_name: str | None = None
    destructive: bool = False
    credential: bool = False

    def to_description(self) -> dict[str, Any]:
        """Return the action- or stream-shaped record the generator understands."""
        described: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "handler": self.id,
            "request": self.request,
        }
        if self.events is not None:
            described["events"] = {kind: schema for kind, schema in self.events.items()}
        else:
            described["result"] = self.result
        if self.request_name is not None:
            described["request_name"] = self.request_name
        if self.result_name is not None:
            described["result_name"] = self.result_name
        described["destructive"] = self.destructive
        described["credential"] = self.credential
        return described
