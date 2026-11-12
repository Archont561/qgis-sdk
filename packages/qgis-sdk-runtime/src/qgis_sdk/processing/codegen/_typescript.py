from __future__ import annotations

import keyword
from collections.abc import Sequence

from qgis_sdk.models import AlgorithmInfo, Catalogue

from ._algorithm import NON_WORD, typescript_type


def emit_typescript_module(
    catalogue: Catalogue,
    providers: Sequence[str] | None = None,
    *,
    package: str = "@archont561/qgis-sdk",
) -> str:
    """One TypeScript module for ``providers`` (default: all in the catalogue)."""
    from ._python import ts_footer, ts_header, ts_shapes

    wanted = (
        tuple(providers)
        if providers is not None
        else tuple(p.id for p in catalogue.providers)
    )
    body, names, used = ts_shapes(catalogue, wanted)
    out = ts_header(catalogue, wanted, body, used, package)
    return ts_footer(out, names)


TS_RUN = """\
/** Run one algorithm of this registry through `qgis.host.algorithms.run`. */
export function runAlgorithm<K extends AlgorithmId>(
\tqgis: AlgorithmHost,
\tid: K,
\tparams: AlgorithmRegistry[K]["params"],
\toptions?: HostInvokeOptions,
): Promise<AlgorithmRun<AlgorithmRegistry[K]["result"]>> {
\treturn runAny<AlgorithmRegistry, K>(qgis, id, params, options);
}"""
TS_VALUE_ALIASES = (
    "Destination",
    "Extent",
    "FileRef",
    "LayerRef",
    "PointValue",
    "RangeValue",
    "VectorLayerInfo",
)


def ts_parameter_lines(algorithm: AlgorithmInfo) -> list[str]:
    from ._python import ts_key

    lines: list[str] = []
    for parameter in algorithm.parameters:
        optional = "" if parameter.required else "?"
        doc = parameter.label or parameter.name
        if parameter.options:
            doc += f" — one of: {', '.join(parameter.options)}"
        lines.append(f"\t/** {_ts_comment(doc)} */")
        lines.append(
            f"\t{ts_key(parameter.name)}{optional}: {typescript_type(parameter)};"
        )
    return lines


def ts_shape(name: str, members: list[str]) -> list[str]:
    """An interface with members, or a closed empty type when there are none."""
    if not members:
        return [f"export type {name} = Record<string, never>;"]
    return [f"export interface {name} {{", *members, "}"]


def ts_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ts_comment(text: str) -> str:
    return text.replace("*/", "* /").replace("\n", " ")


def render_package(
    catalogue: Catalogue, providers: Sequence[str] | None = None, *, init: bool = True
) -> dict[str, str]:
    """Every file of a generated Python package, by name relative to it.

    ``catalogue.json`` holds the catalogue restricted to ``providers`` (the
    fake and ``describe`` read it), one ``<provider>.py`` per provider, and
    ``__init__.py`` unless ``init`` is false (the runtime's own snapshot keeps
    a hand-written init next to the generated modules).
    """
    wanted = (
        tuple(providers)
        if providers is not None
        else tuple(p.id for p in catalogue.providers)
    )
    restricted = Catalogue(
        qgis_version=catalogue.qgis_version,
        providers=tuple(p for p in catalogue.providers if p.id in wanted),
        algorithms=tuple(a for a in catalogue.algorithms if a.provider in wanted),
    )
    files: dict[str, str] = {"catalogue.json": restricted.to_json()}
    for provider in wanted:
        files.update(_provider_files(restricted, provider))
    if init:
        from ._python import emit_python_package_init

        files["__init__.py"] = emit_python_package_init(restricted, wanted)
    return files


def _provider_files(catalogue: Catalogue, provider: str) -> dict[str, str]:
    """One provider's files: a module, or a chunked package when it is large."""
    from ._python import MAX_GENERATED_LINES, emit_python_module, emit_python_package

    module = emit_python_module(catalogue, provider)
    if len(module.splitlines()) <= MAX_GENERATED_LINES:
        return {f"{_module_name(provider)}.py": module}
    package = _module_name(provider)
    return {
        f"{package}/{name}": text
        for name, text in emit_python_package(catalogue, provider).items()
    }


def _module_name(provider: str) -> str:
    """``3d`` -> ``p3d``: a provider id that is not an identifier gets a prefix."""
    name = NON_WORD.sub("_", provider).strip("_").lower() or "provider"
    if name[0].isdigit():
        name = f"p{name}"
    if keyword.iskeyword(name):
        name = f"{name}_"
    return name


module_name = _module_name
