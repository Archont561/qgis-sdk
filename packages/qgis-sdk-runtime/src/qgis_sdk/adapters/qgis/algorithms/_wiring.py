"""PyQGIS-backed ``Algorithms``: QGIS Processing, into new temporary outputs.

Native module: nothing on the pure side may import it. Two things here are worth
knowing before reading the code.

**The chained buffer.** ``native:buffer`` measures in the layer's own units, so
buffering a WGS 84 layer would silently interpret ``distance_metres`` as degrees.
The adapter therefore reprojects the source into the caller's working CRS first
and buffers there. The caller states the CRS; the adapter never picks one, and it
refuses a working CRS that is geographic or whose units are not metres rather
than converting behind the caller's back (decision-19).

**Output ownership.** Omitted destinations are allocated in a run directory;
a qualified named vector destination is staged beside its destination and
published without replacement. Cleanup is best-effort and limited to the
SDK-owned directories. Registered Processing providers are trusted code and
may modify inputs or write elsewhere; their side effects are not sandboxed or
rolled back by this adapter.

Reading cancellation and progress is ``invoke``'s job at phase boundaries. This
adapter deliberately does not claim to abort a native operation mid-flight: a
feedback bridge that raises inside QGIS's own loop has not been qualified here.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis.core import QgsApplication

from qgis_sdk.adapters.qgis.layers import NativeLayers
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    LAYER_KINDS,
    AlgorithmInfo,
    FileRef,
    QgisSdkAlgorithmFailedError,
    QgisSdkAlgorithmRejectedError,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
    RunResult,
    validate_parameters,
)
from qgis_sdk.processing.runs import (
    declared_model_outputs,
    destination_path,
    model_output_names,
    plan_destinations,
)

from ._publish import (
    PublishRequest,
    convert_outputs,
    publish_explicit,
)

if TYPE_CHECKING:
    from qgis_sdk.files import FilesService

    from ._native import NativeAlgorithms


class _ProcessingReady:
    """Whether the Processing framework was initialised in this process."""

    def __init__(self) -> None:
        self.ready = False


_processing_ready = _ProcessingReady()


def processing():
    """Import the Processing framework, initialising it once per process.

    ``from qgis import processing`` is only the shim; the framework itself is the
    plugin, which has to be on ``sys.path`` and initialised. QGIS Desktop does
    both at startup. A headless embedder that has only set the prefix gets the
    plugin directory appended here once, which is the same path QGIS's own
    startup uses.
    """
    try:
        from processing.core.Processing import Processing
    except ImportError:
        plugins = Path(QgsApplication.prefixPath()) / "share" / "qgis" / "python"
        for candidate in (plugins / "plugins",):
            if candidate.is_dir() and str(candidate) not in sys.path:
                sys.path.append(str(candidate))
        try:
            from processing.core.Processing import Processing
        except ImportError as error:
            raise QgisSdkUnsupportedCapabilityError("processing") from error
    if not _processing_ready.ready:
        Processing.initialize()
        _processing_ready.ready = True
    from qgis import processing

    return processing


def _declared_outputs(model: Any) -> dict[str, str]:
    """What a loaded model declares about its exposed outputs, by description.

    ``modelOutputDefinitions`` is the designer's own map, so it survives a
    Processing that answers the derived destination parameters without
    carrying their descriptions. Each entry is keyed twice - by the model
    output's name and by the ``child:output`` destination the run answers
    under - because either can be the name a run produces.
    """
    declared: dict[str, str] = {}
    definitions = getattr(model, "modelOutputDefinitions", None)
    if definitions is None:
        return declared
    for name, output in dict(definitions() or {}).items():
        text = output.description() if hasattr(output, "description") else ""
        if not text:
            continue
        declared[str(name)] = text
        child = output.childId() if hasattr(output, "childId") else ""
        child_output = (
            output.childOutputName() if hasattr(output, "childOutputName") else ""
        )
        if child:
            declared[f"{child}:{child_output or name}"] = text
            declared[f"{child}:{name}"] = text
    return declared


@dataclass(frozen=True, slots=True)
class AlgorithmWiring:
    """The host objects one ``NativeAlgorithms`` backend borrows.

    One record instead of six keyword parameters: the layers, scope, working
    directory, files service and worker backend are the same facts a Desktop
    context and a contract-test fixture assemble, and passing them as a record
    is what keeps the two call sites from drifting apart.
    """

    layers: NativeLayers
    scope: ResourceScope
    working_directory: Path | None = None
    files: FilesService | None = None
    workers: Any | None = None


@dataclass(frozen=True, slots=True)
class RunRequest:
    info: AlgorithmInfo
    params: Mapping[str, object]
    target: Any
    label: str
    rename: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class _NativeParams:
    info: AlgorithmInfo
    params: Mapping[str, object]
    run_directory: Path
    staged: Mapping[str, Path]


@dataclass(slots=True)
class _RunStage:
    owner: NativeAlgorithms
    request: RunRequest
    explicit: Mapping[str, Path]
    processing: Any
    run_directory: Path
    stage: Path | None = None
    staged: dict[str, Path] = field(default_factory=dict)

    def execute(self) -> dict[str, object]:
        self._stage_outputs()
        raw = self._call_processing()
        if self.explicit:
            raw = self._publish(raw)
        if self.request.rename:
            raw = _rename_outputs(raw, self.request.rename)
        return convert_outputs(self.owner, self.request.info, raw)

    def _stage_outputs(self) -> None:
        if not self.explicit:
            return
        name, destination = next(iter(self.explicit.items()))
        try:
            self.stage = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
            )
        except OSError as error:
            raise QgisSdkAlgorithmFailedError(
                self.request.label, "cannot create the output staging directory"
            ) from error
        self.staged[name] = self.stage / destination.name

    def _call_processing(self) -> Mapping[str, Any]:
        native = _native_parameters(
            self.owner,
            _NativeParams(
                info=self.request.info,
                params=self.request.params,
                run_directory=self.run_directory,
                staged=self.staged,
            ),
        )
        try:
            return self.processing.run(self.request.target, native)
        except Exception as error:
            raise QgisSdkAlgorithmFailedError(self.request.label, str(error)) from error

    def _publish(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        return publish_explicit(
            self.owner,
            PublishRequest(
                algorithm=self.request.label,
                raw=raw,
                params=self.request.params,
                explicit=self.explicit,
                staged=self.staged,
                stage=self.stage,
            ),
        )

    def cleanup(self) -> None:
        if self.stage is not None:
            shutil.rmtree(self.stage, ignore_errors=True)


def load_model(owner: NativeAlgorithms, model: FileRef) -> Any:
    from qgis.core import QgsProcessingModelAlgorithm

    loaded = QgsProcessingModelAlgorithm()
    try:
        loaded_from_file = loaded.fromFile(str(owner._resolve(model, "read")))
    except Exception as error:
        raise QgisSdkAlgorithmFailedError(model.name, str(error)) from error
    if not loaded_from_file:
        raise QgisSdkAlgorithmFailedError(
            model.name, f"{model.name} is not a model file this QGIS can load"
        )
    return loaded


def model_run_request(
    owner: NativeAlgorithms,
    loaded: Any,
    model: FileRef,
    params: Mapping[str, object] | None,
) -> RunRequest:
    from ..catalogue import algorithm_info

    declared = {
        **declared_model_outputs(owner._resolve(model, "read")),
        **_declared_outputs(loaded),
    }
    info, output_names = model_output_names(algorithm_info(loaded, "model"), declared)
    return RunRequest(
        info=info,
        params=dict(params or {}),
        target=loaded,
        label=model.name,
        rename=output_names,
    )


def _new_run_directory(owner: NativeAlgorithms, label: str) -> Path:
    run_directory = owner._root / f"run-{owner._runs}"
    try:
        run_directory.mkdir()
    except OSError as error:
        raise QgisSdkAlgorithmFailedError(
            label, "cannot create a new run directory"
        ) from error
    return run_directory


def run_described(owner: NativeAlgorithms, request: RunRequest) -> RunResult:
    validate_parameters(request.info, request.params)
    explicit = plan_destinations(
        request.info, request.params, lambda ref: owner._resolve(ref, "write")
    )
    framework = processing()
    owner._runs += 1
    run_directory = _new_run_directory(owner, request.label)
    stage = _RunStage(
        owner=owner,
        request=request,
        explicit=explicit,
        processing=framework,
        run_directory=run_directory,
    )
    try:
        outputs = stage.execute()
    except BaseException:
        shutil.rmtree(run_directory, ignore_errors=True)
        raise
    finally:
        stage.cleanup()
    return RunResult(algorithm=request.label, outputs=outputs)


def _rename_outputs(
    raw: Mapping[str, Any], rename: Mapping[str, str]
) -> dict[str, Any]:
    lowered = {key.lower(): value for key, value in rename.items()}
    return {lowered.get(key.lower(), key): value for key, value in raw.items()}


def _native_parameters(owner: NativeAlgorithms, ctx: _NativeParams) -> dict[str, Any]:
    native: dict[str, Any] = {}
    for parameter in ctx.info.parameters:
        value = ctx.params.get(parameter.name)
        if parameter.destination:
            native[parameter.name] = _destination_value(owner, ctx, parameter, value)
            continue
        if value is None:
            continue
        native[parameter.name] = _input_value(owner, parameter, value)
    return native


def _destination_value(owner: NativeAlgorithms, ctx: _NativeParams, parameter, value):
    if parameter.name in ctx.staged:
        return str(ctx.staged[parameter.name])
    if value is None:
        return str(destination_path(ctx.run_directory, parameter))
    raise QgisSdkAlgorithmRejectedError(
        ctx.info.id, [f"{parameter.name} was not safely staged"]
    )


def _input_value(owner: NativeAlgorithms, parameter, value):
    if parameter.kind in LAYER_KINDS:
        return _layer_input(owner, value)
    if parameter.kind == "multilayer" and isinstance(value, (list, tuple)):
        return [_layer_input(owner, item) for item in value]
    if isinstance(value, FileRef):
        return str(owner._resolve(value, "read"))
    return value


def _layer_input(owner: NativeAlgorithms, value: object) -> Any:
    """An owned layer id, a readable ref, or an existing source string."""
    if isinstance(value, FileRef):
        return str(owner._resolve(value, "read"))
    if not isinstance(value, str):
        return value
    try:
        return owner._layers._qgs_layer(value)
    except QgisSdkLayerNotFoundError:
        if Path(value).exists() or "://" in value or "|" in value:
            return value
        raise
