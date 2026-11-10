"""The helpers the handlers share: wire shapes, page maths, request building."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass, replace
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.authority import FileOperation, HostAuthority
from qgis_sdk.bridge.host._schemas import (
    DEFAULT_PAGE,
    MAX_FEATURE_PAGE,
    _page,
)
from qgis_sdk.bridge.host._services import HostServices
from qgis_sdk.models import (
    DEFAULT_FEATURE_PAGE,
    AlgorithmInfo,
    FeatureQuery,
    FileRef,
    Geometry,
    LayoutSettings,
    NetworkRequest,
    QgisSdkDecodeError,
    Response,
    RunResult,
)
from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkInvalidRequestError,
)
from qgis_sdk.network.client import NetworkDefaults, build_request

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.bridge.dispatch import ViewBinding


def _plain(value: Any) -> Any:
    """Unwrap a value DTO so the dispatcher's serialization check accepts it."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


def _wire(value: Any) -> Any:
    """Return a model's declared wire shape, falling back to a plain DTO.

    A renderer or a labelling has a ``to_wire`` for the same reason a layer
    description has one: what crosses the wire is a decision the model makes,
    not whatever ``asdict`` happens to flatten.
    """
    writer = getattr(value, "to_wire", None)
    return writer() if callable(writer) else _plain(value)


def _offset(cursor: Any) -> int:
    """Return the offset a cursor encodes; the request schema refused the rest."""
    return 0 if cursor is None else int(cursor)


def _page_of(items: Sequence[Any], payload: Mapping[str, Any]) -> dict:
    """Slice a sequence by the cursor a page sent back."""
    limit = payload.get("limit", DEFAULT_PAGE)
    start = _offset(payload.get("cursor"))
    window = list(items[start : start + limit])
    truncated = start + limit < len(items)
    return _page(
        [_plain(item) for item in window],
        str(start + limit) if truncated else None,
        truncated,
    )


def _layout_settings(payload: Mapping[str, Any]) -> LayoutSettings:
    """Build the render settings a page declared, defaulting what it left out."""
    return LayoutSettings(
        dpi=int(payload.get("dpi", LayoutSettings().dpi)),
        rasterize=bool(payload.get("rasterize", False)),
        georeference=bool(payload.get("georeference", False)),
    )


def _summary(info: AlgorithmInfo) -> dict[str, Any]:
    return {
        "id": info.id,
        "provider": info.provider,
        "name": info.name,
        "label": info.label,
        "group": info.group,
        "deprecated": info.deprecated,
    }


def _algorithm_wire(info: AlgorithmInfo) -> dict[str, Any]:
    """Spell one description with every declared field present.

    A page validates the reply against the generated type, so nothing is left
    to a default the page cannot see.
    """
    return {
        **_summary(info),
        "group_id": info.group_id,
        "help": info.help,
        "parameters": [_parameter_wire(parameter) for parameter in info.parameters],
        "outputs": [
            {"name": output.name, "kind": output.kind, "label": output.label}
            for output in info.outputs
        ],
    }


def _parameter_wire(parameter: Any) -> dict[str, Any]:
    """Spell one parameter, default included, so a page can render its field."""
    has_default = (
        parameter.has_default
        if parameter.has_default is not None
        else parameter.default is not None
    )
    return {
        "name": parameter.name,
        "kind": parameter.kind,
        "label": parameter.label,
        "description": parameter.description,
        "optional": parameter.optional,
        "advanced": parameter.advanced,
        "hidden": parameter.hidden,
        "destination": parameter.destination,
        "required": parameter.required,
        "default_json": json.dumps(parameter.default) if has_default else None,
        "options": list(parameter.options),
        "multiple": parameter.multiple,
        "number_type": parameter.number_type,
        "minimum": parameter.minimum,
        "maximum": parameter.maximum,
        "extension": parameter.extension,
    }


def _resolve_input(authority: HostAuthority, binding: ViewBinding, value: Any) -> Any:
    """Turn a ref the view holds into the path the algorithm reads.

    Only a ref-shaped value is touched; the authority resolves it against the
    calling view, so a ref minted for another view or a forged id is refused
    here before the algorithm sees a parameter. Everything else (a layer id,
    a number, a list) crosses as the page sent it.
    """
    if isinstance(value, Mapping) and value.get("kind") in ("file", "directory"):
        return str(authority.resolve_file(binding, value, FileOperation.READ))
    return value


def _result_for_view(
    services: HostServices, binding: ViewBinding, result: RunResult
) -> dict[str, Any]:
    """Re-mint the refs a run produced so the calling view holds them, not the plugin."""
    outputs: dict[str, object] = {}
    for name, value in result.outputs.items():
        if isinstance(value, FileRef):
            if services.files is None:
                raise QgisSdkBridgeError(
                    "this host has no files service to hand a run's file outputs over"
                )
            path = services.files.resolve(value)
            if value.kind == "directory":
                value = services.authority.grant_directory(binding, path)
            else:
                value = services.authority.grant_file(binding, path)
        outputs[name] = value
    return RunResult(algorithm=result.algorithm, outputs=outputs).to_wire()


def _fetch_request(payload: Mapping[str, Any]) -> NetworkRequest:
    """Turn the declared fetch payload into the request the grant constrains.

    The client's own validation applies (absolute http(s) URL, no user-info);
    the ceilings come from the grant afterwards, so a view asking for more
    gets the grant's limits and one asking for less keeps its own.
    """
    headers = {
        str(item["name"]): str(item["value"]) for item in payload.get("headers", [])
    }
    request = build_request(
        NetworkDefaults(),
        str(payload.get("method", "GET")),
        str(payload["url"]),
        data=payload.get("body"),
        headers=headers,
        timeout=payload.get("timeout_seconds"),
    )
    auth_config = payload.get("auth_config")
    if auth_config is not None:
        request = replace(request, auth_config=str(auth_config))
    return request


def _response_event(response: Response) -> dict[str, Any]:
    text: str | None
    encoded: str | None
    try:
        text, encoded = response.text, None
    except QgisSdkDecodeError:
        text, encoded = None, base64.b64encode(response.content).decode("ascii")
    return {
        "url": response.url,
        "status_code": response.status_code,
        "reason": response.reason,
        "headers": [{"name": n, "value": v} for n, v in response.headers.items()],
        "text": text,
        "base64": encoded,
    }


def _feature_query(payload: Mapping[str, Any]) -> FeatureQuery:
    """Turn a wire request into the bounded query the service takes.

    The bounds are checked here, by name, rather than left to the layer: a page
    asking for more than ``MAX_FEATURE_PAGE`` features or a bbox that is not
    four numbers is a mistake in the request, and the caller hears which.
    """
    raw_bbox = payload.get("bbox")
    raw_ids = payload.get("ids")
    limit = int(payload.get("limit", DEFAULT_FEATURE_PAGE))
    if limit > MAX_FEATURE_PAGE:
        raise QgisSdkInvalidRequestError(
            f"limit is at most {MAX_FEATURE_PAGE} features, not {limit}"
        )
    bbox = None
    if raw_bbox is not None:
        if len(raw_bbox) != 4:
            raise QgisSdkInvalidRequestError(
                f"bbox is (min_x, min_y, max_x, max_y), not {len(raw_bbox)} numbers"
            )
        bbox = tuple(float(item) for item in raw_bbox)
    return FeatureQuery(
        limit=limit,
        cursor=payload.get("cursor"),
        expression=payload.get("expression"),
        bbox=bbox,
        ids=None if raw_ids is None else tuple(int(item) for item in raw_ids),
        encoding=payload.get("encoding", "wkb"),
        with_geometry=bool(payload.get("with_geometry", True)),
    )


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _geometry(value: Any) -> Geometry | None:
    """Read a geometry a page sent back, or ``None`` when it sent none."""
    return None if value is None else Geometry.from_wire(value)
