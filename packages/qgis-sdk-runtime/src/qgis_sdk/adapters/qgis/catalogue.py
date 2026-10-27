"""Read the host's Processing registry into a plain :class:`Catalogue`.

Native module: the only piece of decision-64 that imports QGIS. Everything
downstream - the generator's emitters, the fake, the bridge - consumes the
:class:`~qgis_sdk.models.Catalogue` this produces, so a provider the SDK has
never heard of is described exactly like ``native``.

Run as a module (``python -m qgis_sdk.adapters.qgis.catalogue --out file``)
it starts a headless ``QgsApplication``, initialises Processing, writes the
catalogue as JSON and exits; that is how ``qgis-sdk processing generate``
reads a project's QGIS install without importing QGIS into the tools.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from qgis_sdk.models import (
    DESTINATION_KINDS,
    AlgorithmInfo,
    Catalogue,
    OutputInfo,
    ParameterInfo,
    ProviderInfo,
)

__all__ = ["algorithm_info", "main", "read_catalogue"]

#: ``QgsProcessingParameterNumber`` reports these for "no bound".
_UNBOUNDED = 1e300


def read_catalogue(
    providers: Iterable[str] | None = None, *, registry: Any = None
) -> Catalogue:
    """Describe every algorithm the registry holds, or those of ``providers``.

    Processing is initialised first (the Python providers - ``qgis``,
    ``gdal``, ``grass`` - only register then). Provider ids are matched
    exactly; asking for one the host lacks yields nothing for it rather than
    an error, so a snapshot script can name the core set unconditionally.
    """
    from qgis.core import Qgis, QgsApplication

    from .algorithms import _processing

    _processing()
    if registry is None:
        registry = QgsApplication.processingRegistry()
    wanted = None if providers is None else set(providers)
    provider_infos: list[ProviderInfo] = []
    algorithms: list[AlgorithmInfo] = []
    for provider in sorted(registry.providers(), key=lambda p: p.id()):
        if wanted is not None and provider.id() not in wanted:
            continue
        provider_infos.append(
            ProviderInfo(
                id=provider.id(),
                label=provider.name(),
                version=_text(provider.versionInfo()),
            )
        )
        for algorithm in sorted(provider.algorithms(), key=lambda a: a.id()):
            algorithms.append(algorithm_info(algorithm, provider.id()))
    return Catalogue(
        qgis_version=Qgis.version(),
        providers=tuple(provider_infos),
        algorithms=tuple(algorithms),
    )


def algorithm_info(algorithm: Any, provider_id: str) -> AlgorithmInfo:
    """One registered algorithm as plain data."""
    from qgis.core import Qgis

    flags = algorithm.flags()
    return AlgorithmInfo(
        id=algorithm.id(),
        provider=provider_id,
        name=algorithm.name(),
        label=_text(algorithm.displayName()),
        group=_text(algorithm.group()),
        group_id=_text(algorithm.groupId()),
        help=_text(algorithm.shortHelpString()) or _text(algorithm.shortDescription()),
        deprecated=bool(flags & Qgis.ProcessingAlgorithmFlag.Deprecated),
        parameters=tuple(
            _parameter_info(definition)
            for definition in algorithm.parameterDefinitions()
        ),
        outputs=tuple(
            OutputInfo(
                name=output.name(),
                kind=output.type(),
                label=_text(output.description()),
            )
            for output in algorithm.outputDefinitions()
        ),
    )


def _parameter_info(definition: Any) -> ParameterInfo:
    from qgis.core import Qgis

    flags = definition.flags()
    kind = definition.type()
    default = definition.defaultValue()
    options = _call(definition, "options") or ()
    number_type = None
    minimum = maximum = None
    if kind in ("number", "distance", "area", "scale", "duration"):
        data_type = _call(definition, "dataType")
        if data_type is not None:
            number_type = (
                "integer"
                if data_type == Qgis.ProcessingNumberParameterType.Integer
                else "double"
            )
        minimum = _bound(_call(definition, "minimum"))
        maximum = _bound(_call(definition, "maximum"))
    static_strings = bool(_call(definition, "usesStaticStrings"))
    if kind == "enum" and static_strings and isinstance(default, int):
        # A static-string enum reports its default as a string already; an
        # index would be a lie about what QGIS accepts.
        default = None
    return ParameterInfo(
        name=definition.name(),
        kind=kind,
        label=_text(definition.description()),
        description=_text(_call(definition, "help")),
        optional=bool(flags & Qgis.ProcessingParameterFlag.Optional),
        advanced=bool(flags & Qgis.ProcessingParameterFlag.Advanced),
        hidden=bool(flags & Qgis.ProcessingParameterFlag.Hidden),
        destination=bool(definition.isDestination()) or kind in DESTINATION_KINDS,
        default=_json_default(default),
        has_default=default is not None,
        options=tuple(str(option) for option in options),
        multiple=bool(_call(definition, "allowMultiple")),
        number_type=number_type,
        minimum=minimum,
        maximum=maximum,
        extension=_call(definition, "defaultFileExtension") or None,
    )


def _call(definition: Any, name: str) -> Any:
    method = getattr(definition, name, None)
    if method is None:
        return None
    try:
        return method()
    except TypeError:
        return None


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _bound(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if math.isnan(value) or math.isinf(value) or abs(value) >= _UNBOUNDED:
        return None
    return float(value)


def _json_default(value: Any) -> Any:
    """A default as JSON, or ``None`` when QGIS's value has no JSON shape."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        converted = [_json_default(item) for item in value]
        return converted if all(item is not None for item in converted) else None
    authid = getattr(value, "authid", None)
    if callable(authid):
        return authid() or None
    return None


def _start_application() -> Any:
    """Start a headless ``QgsApplication`` for a subprocess run."""
    from qgis.core import QgsApplication

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    existing = QgsApplication.instance()
    if existing is not None:
        return existing, False
    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        QgsApplication.setPrefixPath(prefix, True)
    application = QgsApplication([b"qgis-sdk-catalogue"], False)
    application.initQgis()
    return application, True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m qgis_sdk.adapters.qgis.catalogue",
        description="Write the host's Processing catalogue as JSON.",
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--provider",
        action="append",
        default=None,
        help="provider id to include (repeatable); default: every provider",
    )
    args = parser.parse_args(argv)
    application, owned = _start_application()
    try:
        catalogue = read_catalogue(args.provider)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(catalogue.to_json(), encoding="utf-8")
    finally:
        if owned:
            application.exitQgis()
    sys.stdout.write(
        f"{len(catalogue.algorithms)} algorithms from "
        f"{len(catalogue.providers)} providers -> {args.out}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - subprocess entry
    raise SystemExit(main())
