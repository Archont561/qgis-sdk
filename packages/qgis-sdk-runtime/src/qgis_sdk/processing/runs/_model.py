"""Model outputs: what a ``.model3`` document says each exposed output is."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

from qgis_sdk.models import AlgorithmInfo, OutputInfo

from ._kinds import DESTINATION_OUTPUT_KINDS

__all__ = ["declared_model_outputs", "model_output_names"]


def _declare_model_output(declared: dict[str, str], entry: ElementTree.Element) -> None:
    """Record one exposed model output under both names it may be answered by."""
    name = entry.get("name") or ""
    fields = {
        option.get("name"): option.get("value") or ""
        for option in entry.findall("Option")
    }
    description = fields.get("description") or ""
    if not name or not description:
        return
    declared[name] = description
    child = fields.get("child_id") or ""
    output = fields.get("output_name") or name
    if child:
        declared[f"{child}:{output}"] = description


def declared_model_outputs(model_file: Path) -> dict[str, str]:
    """What a ``.model3`` document says each exposed output is, by description.

    A model file records its exposed outputs under ``outputs``, each naming
    the child, the child's output and the designer's description. A loaded
    model may answer neither: this Processing derives the destinations from
    the children and hands them back without their descriptions, so the
    document is read for what the designer wrote. Every entry is keyed by the
    ``child:output`` destination the run answers under and by the model
    output's own name, because either can be that name.

    A model file this reader cannot parse answers nothing at all: the naming
    rule then falls back to the child's own name, which is still a true name
    for an output the model does not describe.
    """
    try:
        root = ElementTree.parse(model_file).getroot()
    except (OSError, ElementTree.ParseError):
        return {}
    declared: dict[str, str] = {}
    for section in root.iter("Option"):
        if section.get("name") != "outputs" or section.get("type") != "Map":
            continue
        for entry in section.findall("Option"):
            _declare_model_output(declared, entry)
    return declared


def _derived_name(label: str) -> str:
    """A designer's description as a version-2 output name."""
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _name_tail(name: str) -> str:
    """The child's own name, when no description survives."""
    return name.rsplit(":", 1)[-1].lower()


def _candidate_names(
    info: AlgorithmInfo, declared_text: Mapping[str, str]
) -> dict[str, str]:
    """One name per output definition and per destination parameter."""
    names: dict[str, str] = {}
    for output in info.outputs:
        text = declared_text.get(output.name, output.label)
        names[output.name] = _derived_name(text) or _name_tail(output.name)
    # The destination parameter is the same output seen from the run's side,
    # and its description is the one the designer wrote, so it wins.
    for parameter in info.parameters:
        if not parameter.destination:
            continue
        text = declared_text.get(parameter.name, parameter.label)
        names[parameter.name] = (
            _derived_name(text)
            or names.get(parameter.name)
            or _name_tail(parameter.name)
        )
    return names


def _unique_names(names: Mapping[str, str]) -> dict[str, str]:
    """Disambiguate equal derived names with an ascending numeric suffix."""
    taken: set[str] = set()
    unique: dict[str, str] = {}
    for key, candidate in names.items():
        base = candidate
        suffix = 2
        while candidate in taken:
            candidate = f"{base}_{suffix}"
            suffix += 1
        taken.add(candidate)
        unique[key] = candidate
    return unique


def _described_outputs(
    info: AlgorithmInfo, names: Mapping[str, str]
) -> tuple[OutputInfo, ...]:
    """Rename definitions and add destinations the definitions omit."""
    described = [replace(output, name=names[output.name]) for output in info.outputs]
    declared = {output.name for output in described}
    for parameter in info.parameters:
        if not parameter.destination:
            continue
        candidate = names[parameter.name]
        if candidate in declared:
            continue
        described.append(
            OutputInfo(
                name=candidate,
                kind=DESTINATION_OUTPUT_KINDS.get(parameter.kind, "outputFile"),
                label=parameter.label,
            )
        )
        declared.add(candidate)
    return tuple(described)


def model_output_names(
    info: AlgorithmInfo,
    descriptions: Mapping[str, str] | None = None,
) -> tuple[AlgorithmInfo, dict[str, str]]:
    """A model's outputs, named the way version 2 of the format derives them.

    A model exposes a *child* output, and the child names it after itself
    (``CENTROIDS``); version 2 of the format names the exposed output after
    its description instead - ``Centroids`` becomes ``centroids`` and
    ``Report`` becomes ``report`` - because the child's name belongs to the
    child that writes it. A loaded model describes those outputs twice: as
    output definitions, whose description is often empty and whose name is
    the destination's, and as the destination parameters the format derives,
    whose description is the designer's. The description decides, the tail of
    the child output's name is the fallback, and the mapping answers both the
    description the caller reads (an ``AlgorithmInfo`` whose outputs carry
    the derived names) and the names a run answers under.

    ``descriptions`` is what the loaded model itself declares - keyed by an
    output's own name or by the ``child:output`` destination it exposes - and
    it is the source that survives a QGIS which drops descriptions from the
    parameter definitions. It wins over both.
    """
    declared_text = dict(descriptions or {})
    names = _unique_names(_candidate_names(info, declared_text))
    return replace(info, outputs=_described_outputs(info, names)), names
