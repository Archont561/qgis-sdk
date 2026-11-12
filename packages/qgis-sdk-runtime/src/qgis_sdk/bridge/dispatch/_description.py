from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any

from qgis_sdk.bridge.endpoint._types import (
    Handler,
)
from qgis_sdk.bridge.endpoint._wire import wire_result
from qgis_sdk.bridge.streams import (
    StreamSource,
)
from qgis_sdk.declarations import WIRE_KIND_KEYWORD
from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.models.files import FILE_REF_KINDS, FileRef


def description_parts(
    description: Any,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the advertised description, its actions and its streams as records."""
    if hasattr(description, "to_dict") and hasattr(description, "actions"):
        return (
            description.to_dict(),
            [_action_record(action) for action in description.actions],
            [_stream_record(stream) for stream in getattr(description, "streams", ())],
        )
    if isinstance(description, Mapping):
        return (
            description,
            _declared_records(description, "actions"),
            _declared_records(description, "streams"),
        )
    raise QgisSdkBridgeError(
        "description must be a PluginDescription or a mapping with actions"
    )


def _action_record(action: Any) -> dict[str, Any]:
    """One declared action as the record the wiring reads."""
    return {
        "id": action.id,
        "title": action.title,
        "request": action.request,
        "result": action.result,
    }


def _stream_record(declared: Any) -> dict[str, Any]:
    """One declared stream as the record the wiring reads."""
    return {
        "id": declared.id,
        "title": declared.title,
        "request": declared.request,
        "events": declared.events,
    }


def _declared_records(description: Mapping[str, Any], key: str) -> list[dict]:
    """Return ``description[key]`` as checked records; a missing list is empty."""
    declared = description.get(key, [])
    if not isinstance(declared, list):
        raise QgisSdkBridgeError(f"description.{key} must be a list")
    noun = key[:-1]
    records: list[dict[str, Any]] = []
    for item in declared:
        if not isinstance(item, Mapping):
            raise QgisSdkBridgeError(f"every {noun} in a description must be an object")
        for field_name in ("id", "title"):
            if not isinstance(item.get(field_name), str) or not item[field_name]:
                raise QgisSdkBridgeError(
                    f"{noun} {field_name} must be a nonempty string"
                )
        records.append(dict(item))
    return records


def keyword_handler(
    handler: Callable[..., Any], request: Any, operation_id: str
) -> Handler:
    """Bind a declared action's named-argument payload to the callable.

    A declaration describes the inputs as an object, and the payload is
    validated against that object before this runs, so the only thing left to do
    is spell it as keyword arguments.
    """
    _check_parameter_names(request, operation_id)
    refs = _ref_inputs(request)

    def invoke(payload: Mapping[str, Any]) -> Any:
        if refs:
            payload = {
                key: FileRef.from_wire(value)
                if key in refs and value is not None
                else value
                for key, value in payload.items()
            }
        return wire_result(handler(**payload))

    return invoke


def _ref_inputs(request: Any) -> frozenset[str]:
    """Name the inputs declared as file or directory refs.

    A page sends the ``FileRef`` the host minted as its wire object; the
    handler declared ``FileInput()`` and receives the ref, the way a toolbox
    run and a native form hand it one.
    """
    properties = request.get("properties", {}) if isinstance(request, Mapping) else {}
    names = set()
    for name, schema in properties.items():
        if not isinstance(schema, Mapping):
            continue
        branches = schema.get("anyOf") or [schema]
        for branch in branches:
            intent = (
                branch.get(WIRE_KIND_KEYWORD) if isinstance(branch, Mapping) else None
            )
            if isinstance(intent, Mapping) and intent.get("kind") in FILE_REF_KINDS:
                names.add(name)
    return frozenset(names)


def keyword_source(
    factory: Callable[..., Any], request: Any, operation_id: str
) -> StreamSource:
    """Bind a declared stream's request to its factory, the way actions are bound.

    What the factory yields is handed to the subscription as produced; the
    dataclasses a declared event is spelled with are unwrapped there, so an
    author yields ``Change(...)`` and the view receives the object it declared.
    """
    _check_parameter_names(request, operation_id)

    def open_stream(payload: Mapping[str, Any]) -> Any:
        source = factory(**payload)
        if source is None:
            return None

        def serialize_stream() -> Iterator[Any]:
            try:
                for item in source:
                    yield wire_result(item)
            finally:
                close = getattr(source, "close", None)
                if close is not None:
                    close()

        return serialize_stream()

    return open_stream


def _check_parameter_names(request: Any, operation_id: str) -> None:
    properties: Any = {}
    if isinstance(request, Mapping):
        properties = request.get("properties", {})
    if isinstance(properties, Mapping):
        for name in properties:
            if not isinstance(name, str) or not name.isidentifier():
                raise QgisSdkBridgeError(
                    f"{operation_id}: input {name!r} is not a Python parameter name"
                )
