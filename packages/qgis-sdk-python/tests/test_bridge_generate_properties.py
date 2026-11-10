"""Properties the schema generator must hold for every description it accepts.

The generator writes code a plugin then ships, so its guarantees are about whole
descriptions rather than about one example: the order a plugin declares its
operations in may not reach the module, both modules must name the same
declaration, and a description the SDK would refuse at run time is refused here
instead. The examples live in ``test_bridge_generate.py``; these are the promises
that hold for descriptions nobody wrote down.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk_tools.generate import generate_schema_typescript, generate_typescript
from qgis_sdk_tools.generate._contract import _EVENT_KINDS, PLUGIN_SURFACE

_LEAVES: tuple[dict[str, Any], ...] = (
    {"type": "string"},
    {"type": "integer"},
    {"type": "boolean"},
    {"type": "array", "items": {"type": "string"}},
    {"type": "object", "properties": {"note": {"type": "string"}}},
)
"""Schemas with nothing nested, so a drawn description stays one screen long."""

_SEGMENT = st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5).map(
    lambda text: f"x{text}"
)
"""An id segment: never empty, and never a ``QgisSdk`` member (none has an ``x``)."""

_EMPTY: dict[str, Any] = {"type": "object", "properties": {}}
"""A request that declares no shape: an open map, which renders inline."""

_OPENING = f"export const {PLUGIN_SURFACE.operations_const} = ["
"""Where a rendered module lists its operation ids."""


def _leaf() -> st.SearchStrategy[dict[str, Any]]:
    """One leaf schema, freshly built: identity, not equality, names a type."""
    return st.sampled_from(_LEAVES).map(copy.deepcopy)


@st.composite
def _schemas(draw: st.DrawFn) -> dict[str, Any]:
    """A schema a plugin could declare: a leaf, or one field holding a leaf."""
    leaf = draw(_leaf())
    if draw(st.booleans()):
        return leaf
    return {"type": "object", "properties": {draw(_SEGMENT): leaf}}


@st.composite
def _events(draw: st.DrawFn) -> dict[str, dict[str, Any]]:
    """At least one event kind, drawn from the kinds a frame carries."""
    return draw(st.dictionaries(st.sampled_from(_EVENT_KINDS), _leaf(), min_size=1))


@st.composite
def _descriptions(draw: st.DrawFn) -> dict[str, Any]:
    """One description: actions under ``report``, streams under ``watch``."""
    names = draw(st.lists(_SEGMENT, unique=True, min_size=1, max_size=3))
    streamed = draw(st.lists(_SEGMENT, unique=True, max_size=2))
    described: dict[str, Any] = {
        "id": "acme.reports",
        "actions": [
            {
                "id": f"report.{name}",
                "request": draw(_schemas()),
                "result": draw(_schemas()),
            }
            for name in names
        ],
    }
    if streamed:
        described["streams"] = [
            {
                "id": f"watch.{name}",
                "request": draw(_schemas()),
                "events": draw(_events()),
            }
            for name in streamed
        ]
    return described


def _reversed(described: Mapping[str, Any]) -> dict[str, Any]:
    """The same description with every declared list in the opposite order."""
    backwards = dict(described)
    backwards["actions"] = list(reversed(described["actions"]))
    if "streams" in described:
        backwards["streams"] = list(reversed(described["streams"]))
    return backwards


def _operations(module: str) -> list[str]:
    """The ids a rendered module lists, in the order it lists them."""
    start = module.index(_OPENING) + len(_OPENING)
    return re.findall(r'"([^"]+)"', module[start : module.index("] as const;", start)])


def _constants(module: str) -> dict[str, str]:
    """The ``export const NAME = "value"`` pairs a rendered module carries."""
    return dict(re.findall(r'export const (\w+) = "([^"]*)";', module))


def _declared_ids(described: Mapping[str, Any]) -> list[str]:
    """Every operation id the description declares, in sorted order."""
    declared = [entry["id"] for entry in described["actions"]]
    declared += [entry["id"] for entry in described.get("streams", [])]
    return sorted(declared)


@given(described=_descriptions())
@settings(max_examples=40, deadline=None)
def test_declaration_order_does_not_reach_the_rendered_modules(
    described: dict[str, Any],
) -> None:
    backwards = _reversed(described)
    assert generate_typescript(backwards) == generate_typescript(described)
    assert generate_schema_typescript(backwards) == generate_schema_typescript(
        described
    )


@given(described=_descriptions())
@settings(max_examples=40, deadline=None)
def test_a_module_lists_every_declared_id_once(described: dict[str, Any]) -> None:
    declared = _declared_ids(described)
    assert _operations(generate_typescript(described)) == declared
    assert _operations(generate_schema_typescript(described)) == declared


@given(described=_descriptions())
@settings(max_examples=40, deadline=None)
def test_both_modules_name_the_same_declaration(described: dict[str, Any]) -> None:
    client = _constants(generate_typescript(described))
    schema = _constants(generate_schema_typescript(described))
    fingerprint = PLUGIN_SURFACE.fingerprint_const
    assert schema[fingerprint] in client.values()
    assert client[PLUGIN_SURFACE.id_const] == schema[PLUGIN_SURFACE.id_const]


@given(kind=_SEGMENT)
@settings(max_examples=25, deadline=None)
def test_an_event_kind_the_frame_does_not_carry_is_refused(kind: str) -> None:
    described = {
        "id": "acme.reports",
        "actions": [],
        "streams": [
            {"id": "watch.one", "request": _EMPTY, "events": {kind: _LEAVES[0]}}
        ],
    }
    with pytest.raises(QgisSdkBridgeError, match="not a stream event kind"):
        generate_typescript(described)


@given(name=_SEGMENT)
@settings(max_examples=25, deadline=None)
def test_two_operations_may_not_share_an_id(name: str) -> None:
    operation = {"id": f"report.{name}", "request": _EMPTY, "result": {}}
    described = {"id": "acme.reports", "actions": [operation, dict(operation)]}
    with pytest.raises(QgisSdkBridgeError, match="duplicate operation id"):
        generate_typescript(described)


def test_an_action_that_declares_events_is_refused() -> None:
    described = {
        "id": "acme.reports",
        "actions": [
            {"id": "report.list", "request": _EMPTY, "result": {}, "events": {}}
        ],
    }
    with pytest.raises(QgisSdkBridgeError, match="belongs in description.streams"):
        generate_typescript(described)


def test_a_stream_that_declares_a_result_is_refused() -> None:
    described = {
        "id": "acme.reports",
        "actions": [],
        "streams": [{"id": "watch.one", "request": _EMPTY, "result": {}, "events": {}}],
    }
    with pytest.raises(QgisSdkBridgeError, match="not a result"):
        generate_typescript(described)


def test_a_stream_with_no_event_kind_is_refused() -> None:
    described = {
        "id": "acme.reports",
        "actions": [],
        "streams": [{"id": "watch.one", "request": _EMPTY, "events": {}}],
    }
    with pytest.raises(QgisSdkBridgeError, match="at least one event kind"):
        generate_typescript(described)


def test_two_shapes_declared_under_one_title_are_refused() -> None:
    """A title is a declaration: one title twice has to be one type."""
    first = {
        "type": "object",
        "title": "FileRef",
        "properties": {"id": {"type": "string"}},
    }
    second = {
        "type": "object",
        "title": "FileRef",
        "properties": {"path": {"type": "string"}},
    }
    described = {
        "id": "acme.files",
        "actions": [
            {"id": "files.open", "request": _EMPTY, "result": first},
            {"id": "files.save", "request": _EMPTY, "result": second},
        ],
    }
    with pytest.raises(QgisSdkBridgeError, match="same type name"):
        generate_typescript(described)


def test_one_title_declared_twice_renders_one_interface() -> None:
    titled = {
        "type": "object",
        "title": "FileRef",
        "properties": {"id": {"type": "string"}},
    }
    described = {
        "id": "acme.files",
        "actions": [
            {"id": "files.open", "request": _EMPTY, "result": copy.deepcopy(titled)},
            {"id": "files.save", "request": _EMPTY, "result": copy.deepcopy(titled)},
        ],
    }
    assert generate_typescript(described).count("export interface FileRef {") == 1
