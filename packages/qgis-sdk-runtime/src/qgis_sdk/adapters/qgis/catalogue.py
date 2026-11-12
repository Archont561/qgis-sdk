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


class _CcState1:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn1:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_parameter_info_p1(_s1):
    from qgis.core import Qgis

    _s1.Qgis = Qgis

    _s1.flags = _s1.definition.flags()
    _s1.kind = _s1.definition.type()
    _s1.default = _s1.definition.defaultValue()
    _s1.options = _call(_s1.definition, "options") or ()
    _s1.number_type = None
    _s1.minimum = _s1.maximum = None


def _cc_parameter_info_p2(_s1):
    if _s1.kind in ("number", "distance", "area", "scale", "duration"):
        _s1.data_type = _call(_s1.definition, "dataType")
        if _s1.data_type is not None:
            _s1.number_type = (
                "integer"
                if _s1.data_type == _s1.Qgis.ProcessingNumberParameterType.Integer
                else "double"
            )
        _s1.minimum = _bound(_call(_s1.definition, "minimum"))
        _s1.maximum = _bound(_call(_s1.definition, "maximum"))
    _s1.static_strings = bool(_call(_s1.definition, "usesStaticStrings"))


def _cc_parameter_info_p3(_s1):
    if _s1.kind == "enum" and _s1.static_strings and isinstance(_s1.default, int):
        # A static-string enum reports its default as a string already; an
        # index would be a lie about what QGIS accepts.
        _s1.default = None


def _cc_parameter_info_p4(_s1):
    return _CcReturn1(
        ParameterInfo(
            name=_s1.definition.name(),
            kind=_s1.kind,
            label=_text(_s1.definition.description()),
            description=_text(_call(_s1.definition, "help")),
            optional=bool(_s1.flags & _s1.Qgis.ProcessingParameterFlag.Optional),
            advanced=bool(_s1.flags & _s1.Qgis.ProcessingParameterFlag.Advanced),
            hidden=bool(_s1.flags & _s1.Qgis.ProcessingParameterFlag.Hidden),
            destination=bool(_s1.definition.isDestination())
            or _s1.kind in DESTINATION_KINDS,
            default=_json_default(_s1.default),
            has_default=_s1.default is not None,
            options=tuple(str(option) for option in _s1.options),
            multiple=bool(_call(_s1.definition, "allowMultiple")),
            number_type=_s1.number_type,
            minimum=_s1.minimum,
            maximum=_s1.maximum,
            extension=_call(_s1.definition, "defaultFileExtension") or None,
        )
    )


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_read_catalogue_p1(_s):
    from qgis.core import Qgis, QgsApplication

    _s.Qgis = Qgis
    _s.QgsApplication = QgsApplication

    from .algorithms import _processing

    _s._processing = _processing

    _s._processing()
    if _s.registry is None:
        _s.registry = _s.QgsApplication.processingRegistry()
    _s.wanted = None if _s.providers is None else set(_s.providers)
    _s.provider_infos: list[ProviderInfo] = []
    _s.algorithms: list[AlgorithmInfo] = []


def _cc_read_catalogue_p2(_s):
    for provider in sorted(_s.registry.providers(), key=lambda p: p.id()):
        _s.provider = provider
        if _s.wanted is not None and _s.provider.id() not in _s.wanted:
            continue
        _s.provider_infos.append(
            ProviderInfo(
                id=_s.provider.id(),
                label=_s.provider.name(),
                version=_text(_s.provider.versionInfo()),
            )
        )
        for algorithm in sorted(_s.provider.algorithms(), key=lambda a: a.id()):
            _s.algorithm = algorithm
            _s.algorithms.append(algorithm_info(_s.algorithm, _s.provider.id()))


def _cc_read_catalogue_p3(_s):
    return _CcReturn(
        Catalogue(
            qgis_version=_s.Qgis.version(),
            providers=tuple(_s.provider_infos),
            algorithms=tuple(_s.algorithms),
        )
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
    _s = _CcState(**locals())
    for _p in (_cc_read_catalogue_p1, _cc_read_catalogue_p2, _cc_read_catalogue_p3):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


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
    _s1 = _CcState1(definition=definition)
    for _p1 in (
        _cc_parameter_info_p1,
        _cc_parameter_info_p2,
        _cc_parameter_info_p3,
        _cc_parameter_info_p4,
    ):
        _r1 = _p1(_s1)
        if isinstance(_r1, _CcReturn1):
            return _r1.value
    return None


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
