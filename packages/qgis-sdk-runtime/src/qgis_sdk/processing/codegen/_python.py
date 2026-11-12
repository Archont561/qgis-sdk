from __future__ import annotations

import re
from collections.abc import Sequence

from qgis_sdk.models import AlgorithmInfo, Catalogue, OutputInfo

from ._algorithm import (
    HEADER,
    NON_WORD,
    PYTHON_MODELS,
    PYTHON_OUTPUT_TYPES,
    PYTHON_VALUE_TYPES,
    TYPESCRIPT_OUTPUT_TYPES,
    class_name,
    python_algorithm_tail1,
    python_docstring,
    python_registry_body,
    python_type,
    q,
)
from ._typescript import (
    TS_RUN,
    TS_VALUE_ALIASES,
    ts_parameter_lines,
    ts_shape,
    ts_string,
)


def _python_header(catalogue: Catalogue, provider: str, text: str) -> list[str]:
    """The module docstring and the imports only this provider's text uses."""

    def used(names: Sequence[str]) -> list[str]:
        return [n for n in names if re.search(rf"\b{n}\b", text)]

    typing = ["ClassVar"] + used(["Required"]) + ["TypedDict"]
    header: list[str] = python_docstring(catalogue, provider)
    header.extend(
        [
            "from __future__ import annotations",
            "",
            "from dataclasses import dataclass",
            f"from typing import {', '.join(typing)}",
            "",
            f"from qgis_sdk.models import {', '.join(used(PYTHON_MODELS))}",
        ]
    )
    if used(PYTHON_VALUE_TYPES):
        header.append(
            "from qgis_sdk.processing.types import "
            + ", ".join(used(PYTHON_VALUE_TYPES))
        )
    header.extend(["", ""])
    return header


def emit_python_module(
    catalogue: Catalogue, provider: str, *, module_name: str | None = None
) -> str:
    """The Python module for one provider of ``catalogue``."""
    text, _classes = python_registry_body(catalogue, provider)
    header = _python_header(catalogue, provider, text)
    return "\n".join(header) + text


MAX_GENERATED_LINES = 300
_CHUNK_OVERHEAD = 40


def _python_blocks(
    catalogue: Catalogue, provider: str
) -> list[tuple[str, str, list[str]]]:
    """Per-algorithm ``(id, name, lines)`` for one provider, in catalogue order."""
    algorithms = catalogue.by_provider(provider)
    taken: set[str] = set()
    blocks: list[tuple[str, str, list[str]]] = []
    for algorithm in algorithms:
        name = class_name(algorithm, taken)
        taken.add(name)
        blocks.append((algorithm.id, name, python_algorithm(algorithm, name)))
    return blocks


def _python_chunk_body(blocks: Sequence[tuple[str, str, list[str]]]) -> list[str]:
    """The registry and ``__all__`` for a run of algorithm blocks."""
    body = ["#: Every request class of this provider by algorithm id."]
    body.append("REGISTRY: dict[str, type[TypedRun]] = {")
    body.extend(f"    {q(algorithm_id)}: {name}," for algorithm_id, name, _ in blocks)
    body.append("}")
    body.append("")
    exported = sorted(
        {f"{n}{suffix}" for _, n, _ in blocks for suffix in ("", "Params", "Result")}
    )
    body.append("__all__ = [")
    body.extend(f'    "{name}",' for name in exported)
    body.extend(["]", ""])
    return body


def _python_chunks(
    blocks: Sequence[tuple[str, str, list[str]]],
) -> list[list[tuple[str, str, list[str]]]]:
    """Group blocks so each chunk's file stays under the generated-line limit."""
    chunks: list[list[tuple[str, str, list[str]]]] = []
    current: list[tuple[str, str, list[str]]] = []
    cost = _CHUNK_OVERHEAD
    for block in blocks:
        block_cost = len(block[2]) + 4  # the block, its registry and ``__all__`` lines
        if current and cost + block_cost > MAX_GENERATED_LINES:
            chunks.append(current)
            current = []
            cost = _CHUNK_OVERHEAD
        current.append(block)
        cost += block_cost
    if current:
        chunks.append(current)
    return chunks


def emit_python_package(catalogue: Catalogue, provider: str) -> dict[str, str]:
    """The files of a provider too large for one module: chunked submodules.

    ``<provider>/__init__.py`` re-exports every request class, ``REGISTRY`` and
    ``ALGORITHM_IDS`` from ``<provider>/_<n>.py`` chunks, so
    ``qgis_sdk.processing.<provider>`` keeps the one-module shape a caller
    imports while no single file carries the whole catalogue.
    """
    blocks = _python_blocks(catalogue, provider)
    chunks = _python_chunks(blocks)
    files = {
        f"_{index}.py": _python_chunk_file(catalogue, provider, chunk)
        for index, chunk in enumerate(chunks)
    }
    files["__init__.py"] = _python_package_init(catalogue, provider, len(chunks))
    return files


def _python_chunk_file(
    catalogue: Catalogue, provider: str, chunk: Sequence[tuple[str, str, list[str]]]
) -> str:
    """One chunk submodule: its algorithm blocks, registry and ``__all__``."""
    body: list[str] = []
    for _algorithm_id, _name, lines in chunk:
        body.extend(lines)
    body.extend(_python_chunk_body(chunk))
    text = "\n".join(body)
    return "\n".join(_python_header(catalogue, provider, text)) + text


def _python_package_init(catalogue: Catalogue, provider: str, chunks: int) -> str:
    """The aggregating ``__init__`` of a chunked provider package."""
    names = ", ".join(f"_{index}" for index in range(chunks))
    lines = python_docstring(catalogue, provider)
    lines.extend(["from __future__ import annotations", "", f"from . import {names}"])
    lines.extend(f"from ._{index} import *" for index in range(chunks))
    lines.extend(
        [
            "",
            f"PROVIDER = {q(provider)}",
            "",
            f"_chunks = ({names},)",
            "REGISTRY: dict[str, type[TypedRun]] = {}",
            "for _chunk in _chunks:",
            "    REGISTRY.update(_chunk.REGISTRY)",
            "",
            "ALGORITHM_IDS: tuple[str, ...] = tuple(REGISTRY)",
            "",
            '__all__ = ["ALGORITHM_IDS", "PROVIDER", "REGISTRY"] + [',
            "    name for _chunk in _chunks for name in _chunk.__all__",
            "]",
            "",
        ]
    )
    return "\n".join(lines)


def python_algorithm(algorithm: AlgorithmInfo, name: str) -> list[str]:
    lines: list[str] = []
    # Params TypedDict with the QGIS names (functional form: GRASS flags are
    # not identifiers).
    entries: list[str] = []
    for parameter in algorithm.parameters:
        annotation = python_type(parameter)
        if parameter.required:
            annotation = f"Required[{annotation}]"
        entries.append(f"        {q(parameter.name)}: {annotation},")
    lines.extend(_typed_dict(f"{name}Params", entries))
    lines.extend(
        _typed_dict(
            f"{name}Result",
            [f"        {q(o.name)}: {_python_output(o)}," for o in algorithm.outputs],
        )
    )
    lines.append("")
    lines.append("")
    return python_algorithm_tail1(**{**globals(), **locals()})


def _typed_dict(name: str, entries: Sequence[str]) -> list[str]:
    """A functional ``TypedDict`` as ``ruff format`` lays it out."""
    if not entries:
        return [
            f"{name} = TypedDict(",
            f'    "{name}",',
            "    {},",
            "    total=False,",
            ")",
        ]
    return [
        f"{name} = TypedDict(",
        f'    "{name}",',
        "    {",
        *entries,
        "    },",
        "    total=False,",
        ")",
    ]


def _python_output(output: OutputInfo) -> str:
    return PYTHON_OUTPUT_TYPES.get(output.kind, "object")


def emit_python_package_init(catalogue: Catalogue, providers: Sequence[str]) -> str:
    """The ``__init__`` of a generated package: the catalogue and its providers."""
    return "\n".join(
        [
            f'"""{HEADER.format(version=catalogue.qgis_version)}',
            "",
            "The catalogue these modules were generated from is ``catalogue.json``",
            "next to this file; ``CATALOGUE`` loads it once. Import a provider",
            "module (``from <this package> import native``) for its request classes.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "from pathlib import Path",
            "",
            "from qgis_sdk.processing.snapshot import load_catalogue",
            "",
            f"QGIS_VERSION = {q(catalogue.qgis_version)}",
            "PROVIDERS: tuple[str, ...] = ("
            + "".join(f"{q(p)}, " for p in providers)
            + ")",
            'CATALOGUE = load_catalogue(Path(__file__).with_name("catalogue.json"))',
            "",
            '__all__ = ["CATALOGUE", "PROVIDERS", "QGIS_VERSION"]',
            "",
        ]
    )


def _ts_prefix(provider_id: str) -> str:
    """``native`` -> ``Native``, ``3d`` -> ``P3d``: the per-provider type prefix."""
    provider = "".join(w[:1].upper() + w[1:] for w in NON_WORD.split(provider_id) if w)
    if provider[:1].isdigit():
        provider = f"P{provider}"
    return provider


def ts_key(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else f'"{name}"'


def _ts_algorithm_shape(
    algorithm: AlgorithmInfo, taken: dict[str, set[str]]
) -> tuple[str, list[str]]:
    """One algorithm's Params/Result interfaces, with a collision-free name."""
    base = class_name(algorithm, taken.setdefault(algorithm.provider, set()))
    taken[algorithm.provider].add(base)
    name = _ts_prefix(algorithm.provider) + base
    shape = [f"/** {algorithm.label} (`{algorithm.id}`). */"]
    shape.extend(ts_shape(f"{name}Params", ts_parameter_lines(algorithm)))
    shape.extend(
        ts_shape(
            f"{name}Result",
            [
                f"\t{ts_key(output.name)}?: "
                f"{TYPESCRIPT_OUTPUT_TYPES.get(output.kind, 'unknown')};"
                for output in algorithm.outputs
            ],
        )
    )
    shape.append("")
    return name, shape


def ts_shapes(
    catalogue: Catalogue, wanted: tuple[str, ...]
) -> tuple[list[str], list[tuple[str, str]], set[str]]:
    """The parameter/result shapes for every wanted algorithm, and used aliases."""
    algorithms = [a for a in catalogue.algorithms if a.provider in wanted]
    body: list[str] = []
    names: list[tuple[str, str]] = []
    taken: dict[str, set[str]] = {}
    for algorithm in algorithms:
        name, shape = _ts_algorithm_shape(algorithm, taken)
        names.append((algorithm.id, name))
        body.extend(shape)
    used = {
        alias
        for alias in TS_VALUE_ALIASES
        if any(re.search(rf"\b{alias}\b", line) for line in body)
    }
    return body, names, used


def _ts_imports(used: set[str]) -> list[str]:
    """Only the value aliases the shapes use, plus the fixed runner imports."""
    return sorted(
        [f"\ttype {alias}," for alias in used]
        + [
            "\ttype AlgorithmHost,",
            "\ttype AlgorithmRun,",
            "\ttype HostInvokeOptions,",
            "\trunAlgorithm as runAny,",
        ],
        key=lambda line: line.replace("\ttype ", "\t").lower(),
    )


def ts_header(
    catalogue: Catalogue,
    wanted: tuple[str, ...],
    body: Sequence[str],
    used: set[str],
    package: str,
) -> list[str]:
    """The file header, its imports and the algorithm shapes."""
    return [
        f"// {HEADER.format(version=catalogue.qgis_version)}",
        "// Regenerate with `qgis-sdk processing generate`; CI fails when this file is stale.",
        "",
        "import {",
        *_ts_imports(used),
        f'}} from "{package}";',
        "",
        f"export const QGIS_VERSION = {ts_string(catalogue.qgis_version)};",
        f"export const PROVIDERS = [{', '.join(ts_string(p) for p in wanted)}] as const;",
        "",
        *body,
    ]


def ts_footer(out: list[str], names: Sequence[tuple[str, str]]) -> str:
    """The registry, ids and bound runner appended after the shapes."""
    out.append(
        "/** Every generated algorithm by id; `runAlgorithm` is generic over it. */"
    )
    out.append("export interface AlgorithmRegistry {")
    for algorithm_id, name in names:
        out.append(
            f'\t"{algorithm_id}": {{ params: {name}Params; result: {name}Result }};'
        )
    out.append("}")
    out.append("")
    out.append("export const ALGORITHM_IDS = [")
    out.extend(f'\t"{algorithm_id}",' for algorithm_id, _ in names)
    out.append("] as const;")
    out.append("")
    out.append("export type AlgorithmId = keyof AlgorithmRegistry;")
    out.append("")
    out.extend(TS_RUN.splitlines())
    out.append("")
    return "\n".join(out)
