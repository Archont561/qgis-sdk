"""The JSON Schemas of the curated host surface: pages, layers, fetch and algorithms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qgis_sdk.bridge.authority import FILE_REF

#: Rows a page gets when it does not ask for a size.
DEFAULT_PAGE = 50

#: Ceiling for one page: a page that asks for a million rows gets fifty.
MAX_PAGE = 200

GUI = "gui"
WORKER = "worker"


def _object(properties: Mapping[str, Any], required: Sequence[str] = ()) -> dict:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


def _array(items: Mapping[str, Any]) -> dict:
    return {"type": "array", "items": items}


#: One schema object, reused by every operation that returns a layer, so the
#: generated module names it once and both a get and a page item share the type.
VECTOR_LAYER_INFO = _object(
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "geometry_type": {"enum": ["point", "line", "polygon", "none"]},
        "field_names": _array({"type": "string"}),
        "crs": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    required=("id", "name", "geometry_type", "field_names", "crs"),
)
VECTOR_LAYER_INFO["title"] = "VectorLayerInfo"

#: The paging request, also shared: a page size and a cursor. The cursor is the
#: offset this module issued in ``next_cursor``, encoded as a decimal string, so
#: the declared pattern refuses anything else before a handler runs - reading a
#: malformed cursor as "start over" would restart the first page in silence.
PAGE_REQUEST = _object(
    {
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE},
        "cursor": {"type": "string", "pattern": "[0-9]+"},
    }
)

_NOTHING = {"type": "null"}
_TEXT_OR_NULL = {"anyOf": [{"type": "string"}, {"type": "null"}]}

#: One HTTP header, as a name/value pair: a list of these is a wire shape every
#: generator can type, where a free-form map is not.
HTTP_HEADER = _object(
    {"name": {"type": "string"}, "value": {"type": "string"}},
    required=("name", "value"),
)
HTTP_HEADER["title"] = "HttpHeader"

FETCH_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
MAX_FETCH_TIMEOUT_SECONDS = 300

#: What a view may say about a request. The URL is absolute; the view's grant
#: decides whether its origin, the method and the authentication are allowed,
#: and the host's limits cap the body and the redirects whatever is asked.
FETCH_REQUEST = _object(
    {
        "url": {"type": "string"},
        "method": {"enum": list(FETCH_METHODS)},
        "headers": _array(HTTP_HEADER),
        "body": {"type": "string"},
        "timeout_seconds": {
            "type": "number",
            "minimum": 0.1,
            "maximum": MAX_FETCH_TIMEOUT_SECONDS,
        },
        "auth_config": {"type": "string"},
    },
    required=("url",),
)

#: The one event a fetch emits. ``text`` is the body decoded with its declared
#: charset (UTF-8 when none); a body that is not text crosses as ``base64``.
FETCH_RESPONSE = _object(
    {
        "url": {"type": "string"},
        "status_code": {"type": "integer"},
        "reason": {"type": "string"},
        "headers": _array(HTTP_HEADER),
        "text": _TEXT_OR_NULL,
        "base64": _TEXT_OR_NULL,
    },
    required=("url", "status_code", "reason", "headers", "text", "base64"),
)

_SCALAR = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "null"},
    ]
}

#: One registered Processing provider.
PROVIDER_INFO = _object(
    {
        "id": {"type": "string"},
        "label": {"type": "string"},
        "version": {"type": "string"},
    },
    required=("id", "label", "version"),
)
PROVIDER_INFO["title"] = "ProviderInfo"

#: One row of ``algorithms.list``: enough to fill a picker, not the help.
ALGORITHM_SUMMARY = _object(
    {
        "id": {"type": "string"},
        "provider": {"type": "string"},
        "name": {"type": "string"},
        "label": {"type": "string"},
        "group": {"type": "string"},
        "deprecated": {"type": "boolean"},
    },
    required=("id", "provider", "name", "label", "group", "deprecated"),
)
ALGORITHM_SUMMARY["title"] = "AlgorithmSummary"

#: One parameter as ``algorithms.describe`` reports it. ``default_json`` is the
#: default as JSON text (``null`` when the registry declares none): a default
#: can be a list or an object, which the wire dialect cannot type otherwise.
PARAMETER_INFO = _object(
    {
        "name": {"type": "string"},
        "kind": {"type": "string"},
        "label": {"type": "string"},
        "description": {"type": "string"},
        "optional": {"type": "boolean"},
        "advanced": {"type": "boolean"},
        "hidden": {"type": "boolean"},
        "destination": {"type": "boolean"},
        "required": {"type": "boolean"},
        "default_json": _TEXT_OR_NULL,
        "options": _array({"type": "string"}),
        "multiple": {"type": "boolean"},
        "number_type": _TEXT_OR_NULL,
        "minimum": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "maximum": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "extension": _TEXT_OR_NULL,
    },
    required=(
        "name",
        "kind",
        "label",
        "description",
        "optional",
        "advanced",
        "hidden",
        "destination",
        "required",
        "default_json",
        "options",
        "multiple",
        "number_type",
        "minimum",
        "maximum",
        "extension",
    ),
)
PARAMETER_INFO["title"] = "ParameterInfo"

OUTPUT_INFO = _object(
    {
        "name": {"type": "string"},
        "kind": {"type": "string"},
        "label": {"type": "string"},
    },
    required=("name", "kind", "label"),
)
OUTPUT_INFO["title"] = "OutputInfo"

#: The full description one ``algorithms.describe`` returns.
ALGORITHM_INFO = _object(
    {
        "id": {"type": "string"},
        "provider": {"type": "string"},
        "name": {"type": "string"},
        "label": {"type": "string"},
        "group": {"type": "string"},
        "group_id": {"type": "string"},
        "help": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "parameters": _array(PARAMETER_INFO),
        "outputs": _array(OUTPUT_INFO),
    },
    required=(
        "id",
        "provider",
        "name",
        "label",
        "group",
        "group_id",
        "help",
        "deprecated",
        "parameters",
        "outputs",
    ),
)
ALGORITHM_INFO["title"] = "AlgorithmInfo"

#: What a page sends to run: the id and the parameters as the generated
#: ``<Provider><Algorithm>Params`` type spells them. Layer inputs are owned
#: layer ids; file inputs are refs this host minted for the view; the host
#: validates the map against the algorithm's description before anything runs.
RUN_REQUEST = _object(
    {
        "algorithm_id": {"type": "string"},
        "params": {"type": "object"},
    },
    required=("algorithm_id", "params"),
)

#: One output of a run, tagged by what it is: an owned vector layer, a file or
#: directory ref minted for the calling view, or a scalar.
RUN_OUTPUT = _object(
    {
        "name": {"type": "string"},
        "kind": {"enum": ["vector", "file", "value"]},
        "layer": VECTOR_LAYER_INFO,
        "file": FILE_REF,
        "value": _SCALAR,
    },
    required=("name", "kind"),
)
RUN_OUTPUT["title"] = "RunOutput"

RUN_RESULT = _object(
    {"algorithm": {"type": "string"}, "outputs": _array(RUN_OUTPUT)},
    required=("algorithm", "outputs"),
)
RUN_RESULT["title"] = "RunResult"


def _page(items: Sequence[Any], cursor: str | None, truncated: bool) -> dict:
    """Shape one page, with the cursor only when something is left."""
    page: dict[str, Any] = {"items": list(items), "truncated": truncated}
    if truncated:
        page["next_cursor"] = cursor
    return page


def _page_result(items: Mapping[str, Any]) -> dict:
    return _object(
        {
            "items": _array(items),
            "truncated": {"type": "boolean"},
            "next_cursor": {"type": "string"},
        },
        required=("items", "truncated"),
    )
