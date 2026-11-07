"""Expose a ``Provider`` as a QGIS Processing provider.

``NativeProcessing`` is the ``ctx.processing`` service of a QGIS Desktop host:
``PluginRuntime.start()`` hands it every provider the plugin lists in
``providers = [...]`` (decision-42), and the provider becomes visible where QGIS
users look for algorithms: the Processing toolbox, ``processing.run("provider:
algorithm", ...)``, the modeler and batch mode. Nothing about an algorithm
function changes - the bridge builds the ``QgsProcessingAlgorithm`` around it
and calls it through the same ``invoke`` an action uses, with the same
``AlgorithmContext`` type.

Two decisions worth reading before the code:

**Parameters come from the function's inputs.** Every input was already mapped
to a parameter kind when the provider declared it (``qgis_sdk.algorithms``), so
this module only has to translate a kind into a ``QgsProcessingParameter`` and
the widget value back into the keyword. An input that could not be mapped never
reached here, which is why there is no fallback widget below.

**Each output kind is published its own way.** The function's result kind
(the ``qgis_sdk.models`` output kind table) decides what the dialog offers
and where the result lands: a produced vector layer is copied feature by
feature into whatever sink the user chose, a produced raster or file is
copied into the chosen destination, a produced folder or several layers are
written into the chosen folder, a report is saved as its ``.html``, and a
number, string or boolean is handed back as the value itself. That keeps
decision-19's "explicit destination" and leaves the produced temporary
artifacts untouched for the caller's own cleanup.

``FlagNoThreading`` is deliberate: this library has not qualified running these
adapters on a Processing worker thread, so the bridge tells QGIS to execute on the
thread it was qualified on instead of claiming a safety it cannot show.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsFeature,
    QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingOutputBoolean,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputHtml,
    QgsProcessingOutputMultipleLayers,
    QgsProcessingOutputNumber,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputString,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterColor,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsProcessingProvider,
    QgsVectorFileWriter,
)
from qgis.PyQt.QtGui import QColor

from qgis_sdk.algorithms import (
    CRS_PARAMETER,
    LAYER_PARAMETER,
    METRES_PARAMETER,
    AlgorithmDescription,
    invoke,
)
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.core import AlgorithmContext, ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import (
    ColourParameter,
    FieldParameter,
    FileParameter,
    LayerParameter,
    MetresParameter,
    RangeParameter,
    output_kinds,
    parameter_kinds,
)
from qgis_sdk.providers import Provider

from .algorithms import NativeAlgorithms, _processing
from .layers import NativeLayers
from .project import NativeProject
from .rasters import NativeRasters

__all__ = ["NativeProcessing", "NativeProcessingProvider"]

OUTPUT_PARAMETER = "OUTPUT"


class _FeedbackProgress:
    """Forward an execution's fraction to the dialog's progress bar."""

    def __init__(self, feedback: QgsProcessingFeedback) -> None:
        self._feedback = feedback

    def report(self, fraction: float) -> None:
        self._feedback.setProgress(int(fraction * 100))


class _FeedbackCancellation:
    """Read cancellation from the Processing feedback, not from a second source."""

    def __init__(self, feedback: QgsProcessingFeedback) -> None:
        self._feedback = feedback

    def is_cancelled(self) -> bool:
        return self._feedback.isCanceled()


#: The Processing parameter classes the kind registry names, by class name.
#: A kind naming a class absent here fails the registry test, not a toolbox.
_PARAMETER_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        QgsProcessingParameterBoolean,
        QgsProcessingParameterColor,
        QgsProcessingParameterCrs,
        QgsProcessingParameterEnum,
        QgsProcessingParameterField,
        QgsProcessingParameterFile,
        QgsProcessingParameterMapLayer,
        QgsProcessingParameterNumber,
        QgsProcessingParameterRasterLayer,
        QgsProcessingParameterString,
        QgsProcessingParameterVectorLayer,
    )
}

#: The Processing output classes the result kind table names, by class name.
#: A kind naming a class absent here fails the registry test, not a toolbox.
_OUTPUT_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        QgsProcessingOutputBoolean,
        QgsProcessingOutputFile,
        QgsProcessingOutputFolder,
        QgsProcessingOutputHtml,
        QgsProcessingOutputMultipleLayers,
        QgsProcessingOutputNumber,
        QgsProcessingOutputRasterLayer,
        QgsProcessingOutputString,
        QgsProcessingOutputVectorLayer,
    )
}

#: Where a run of each result kind writes: the destination parameter class the
#: dialog offers and its options. A kind absent here (number, string, boolean)
#: hands its result back as a value with no destination to choose.
_DESTINATION_CLASSES: dict[str, tuple[type, dict[str, Any]]] = {
    "outputVector": (QgsProcessingParameterFeatureSink, {}),
    "outputRaster": (QgsProcessingParameterRasterDestination, {}),
    "outputFile": (QgsProcessingParameterFileDestination, {}),
    "outputFolder": (QgsProcessingParameterFolderDestination, {}),
    "outputHtml": (
        QgsProcessingParameterFileDestination,
        {"fileFilter": "HTML files (*.html)"},
    ),
    "outputMultilayer": (QgsProcessingParameterFolderDestination, {}),
}

#: The result name of a multiple-layers output; every other kind shares the
#: one output and destination name.
MULTI_OUTPUT_NAME = "OUTPUTS"


def _rasters_of(bridge: Any) -> Any:
    """Return the provider's raster service, or refuse a raster input by name."""
    rasters = getattr(bridge, "rasters", None)
    if rasters is None:
        raise QgsProcessingException(
            "this host has no raster service, so a raster input cannot be read"
        )
    return rasters


def _files_of(bridge: Any) -> Any:
    """Return the files service that resolves a produced ref, or ``None``.

    The bridge resolves a handler's ``FileRef`` result through the same files
    service the run machinery owns, so a file output is published from the
    exact path the ref names and nothing else.
    """
    return getattr(bridge.algorithm_service, "_files", None)


#: The ``Qgis::ProcessingSourceType`` a map-layer parameter is narrowed to, per
#: layer kind.
#:
#: QGIS 3.44 has a parameter class of its own only for a vector and for a raster
#: layer; the other kinds exist as *source types*, which is what
#: ``QgsProcessingParameterMapLayer.setDataTypes`` restricts a parameter to. So a
#: mesh input is a map-layer parameter narrowed to ``Mesh`` rather than a
#: ``QgsProcessingParameterMeshLayer`` class that no QGIS release has. A tiled
#: scene is deliberately absent: ``Qgis::ProcessingSourceType`` gains
#: ``TiledScene`` only in QGIS 4.0, so that input stays an unrestricted
#: map-layer parameter - a restriction the running Processing does not know would
#: refuse the toolbox silently.
_LAYER_SOURCE_TYPES: dict[str, str] = {
    "mesh": "Mesh",
    "point_cloud": "PointCloud",
    "vector_tile": "VectorTile",
    "annotation": "Annotation",
}


def _marker(annotation: Any, marker_type: type) -> Any:
    if get_origin(annotation) is not Annotated:
        return None
    return next(
        (m for m in get_args(annotation)[1:] if isinstance(m, marker_type)), None
    )


def _parameter(kind: str, name: str, annotation: Any = None) -> Any:
    """Build the Processing parameter a declared kind deserves."""
    cls = _PARAMETER_CLASSES[parameter_kinds()[kind].processing]
    if kind == LAYER_PARAMETER:
        # A layer input names its kind (TASK-87, TASK-91), and the kind decides
        # what the toolbox offers: a dedicated class where Processing has one, a
        # map-layer parameter narrowed to that kind's source type where it does
        # not - never a filter the parameter can ignore.
        wanted = (_marker(annotation, LayerParameter) or LayerParameter()).kind
        if wanted == "vector":
            return QgsProcessingParameterVectorLayer(name, name)
        if wanted == "raster":
            return QgsProcessingParameterRasterLayer(name, name)
        parameter = QgsProcessingParameterMapLayer(name, name)
        source_type = _LAYER_SOURCE_TYPES.get(wanted)
        if source_type is not None:
            parameter.setDataTypes([getattr(Qgis.ProcessingSourceType, source_type)])
        return parameter
    if kind == METRES_PARAMETER:
        metres = _marker(annotation, MetresParameter) or MetresParameter()
        parameter = cls(
            name,
            f"{name} (metres)",
            type=QgsProcessingParameterNumber.Double,
            minValue=metres.minimum,
        )
        if metres.maximum is not None:
            parameter.setMaximum(metres.maximum)
        return parameter
    if kind == CRS_PARAMETER:
        return cls(name, name)
    if kind == "file":
        filters = (_marker(annotation, FileParameter) or FileParameter()).filters
        return cls(
            name,
            name,
            behavior=QgsProcessingParameterFile.Behavior.File,
            fileFilter=";;".join(_qt_filter(glob) for glob in filters),
        )
    if kind == "directory":
        return cls(name, name, behavior=QgsProcessingParameterFile.Behavior.Folder)
    if kind == "field":
        return cls(name, name, parentLayerParameterName=_field_parent(annotation))
    if kind == "range":
        bounds = _marker(annotation, RangeParameter)
        integral = isinstance(bounds.minimum, int) and isinstance(bounds.maximum, int)
        return cls(
            name,
            name,
            type=QgsProcessingParameterNumber.Integer
            if integral
            else QgsProcessingParameterNumber.Double,
            minValue=bounds.minimum,
            maxValue=bounds.maximum,
        )
    if kind == "colour":
        colour = _marker(annotation, ColourParameter) or ColourParameter()
        return cls(name, name, opacityEnabled=colour.alpha)
    if kind == "enum":
        return cls(name, name, options=list(get_args(annotation)))
    if kind == "string":
        return cls(name, name)
    if kind == "integer":
        return cls(name, name, type=QgsProcessingParameterNumber.Integer)
    if kind == "number":
        return cls(name, name, type=QgsProcessingParameterNumber.Double)
    if kind == "boolean":
        return cls(name, name)
    raise QgisSdkDeclarationError(f"unsupported parameter kind {kind!r}")


def _qt_filter(glob: str) -> str:
    """Spell one author glob the way a Qt file dialog lists it: ``CSV (*.csv)``."""
    stem, dot, extension = glob.rpartition(".")
    label = extension.upper() if stem == "*" and dot else glob
    return f"{label} ({glob})"


def _field_parent(annotation: Any) -> str:
    return _marker(annotation, FieldParameter).of


def _hex_rgba(colour: QColor, *, alpha: bool) -> str:
    """Spell a QColor the way the colour kind stores it: ``#RRGGBBAA``."""
    rgb = colour.name(QColor.NameFormat.HexRgb)
    return f"{rgb}{colour.alpha():02x}" if alpha else rgb


class _BridgeAlgorithm(QgsProcessingAlgorithm):
    """One registered algorithm, presented as a native Processing algorithm."""

    def __init__(
        self, bridge: NativeProcessingProvider, description: AlgorithmDescription
    ) -> None:
        super().__init__()
        self._bridge = bridge
        self._description = description

    def name(self) -> str:
        return self._description.id

    def displayName(self) -> str:
        return self._description.title

    def group(self) -> str:
        return self._description.group or ""

    def groupId(self) -> str:
        return self._description.group or ""

    def shortHelpString(self) -> str:
        return (
            f"{self._description.title} (qgis-sdk provider {self._bridge.provider_id})"
        )

    def initAlgorithm(self, config: dict | None = None) -> None:
        for name, kind in self._description.kinds.items():
            self.addParameter(
                _parameter(kind, name, self._description.annotations[name])
            )
        kind = output_kinds()[self._description.result_kind]
        destination = _DESTINATION_CLASSES.get(kind.name)
        if destination is not None:
            destination_class, options = destination
            # ``createOutput=False``: the automatic output a destination
            # parameter would add has the parameter's own type, which is wrong
            # where the result kind is an HTML report or several layers - the
            # declared output below is the one true face.
            self.addParameter(
                destination_class(OUTPUT_PARAMETER, "Output", **options), False
            )
        output_name = (
            MULTI_OUTPUT_NAME if kind.name == "outputMultilayer" else OUTPUT_PARAMETER
        )
        self.addOutput(_OUTPUT_CLASSES[kind.processing](output_name, "Output"))

    def flags(self) -> QgsProcessingAlgorithm.Flag:
        return QgsProcessingAlgorithm.FlagNoThreading

    def createInstance(self) -> _BridgeAlgorithm:
        return _BridgeAlgorithm(self._bridge, self._description)

    def processAlgorithm(
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        """Run the author's function and hand its output to the chosen sink.

        The function runs through ``invoke`` from an ``AlgorithmContext`` the
        bridge builds over the dialog's feedback: the same runner, the same
        context type and the same ordering an action or a job gets, so the
        toolbox cannot behave differently from the plugin's own call.
        """
        minted: list[str] = []
        values = {
            name: self._value(name, kind, parameters, context, minted)
            for name, kind in self._description.kinds.items()
        }
        scope = self._bridge.scope.child()
        try:
            toolbox = AlgorithmContext(
                progress=_FeedbackProgress(feedback),
                cancellation=_FeedbackCancellation(feedback),
                scope=scope,
                algorithms=self._bridge.algorithm_service,
                project=self._bridge.project,
            )
            result = invoke(
                self._bridge.function_for(self._description.id),
                toolbox,
                add_to_project=False,
                **values,
            )
        finally:
            scope.close()
            # The refs minted for this run were the dialog's picker results;
            # they expire with the run, like a view's refs with the view.
            for ref_id in minted:
                self._bridge.authority.revoke(ref_id)
        return self._publish(result, parameters, context)

    def _publish(
        self, result: Any, parameters: dict, context: QgsProcessingContext
    ) -> dict:
        """Hand the produced output to the destination its kind publishes to."""
        kind = output_kinds()[self._description.result_kind]
        if kind.name == "outputVector":
            return {
                OUTPUT_PARAMETER: self._copy_to_sink(result.id, parameters, context)
            }
        if kind.name == "outputRaster":
            source = Path(_rasters_of(self._bridge)._qgs_raster(result.id).source())
            return {OUTPUT_PARAMETER: self._copy_file(source, parameters, context)}
        if kind.name in ("outputFile", "outputHtml"):
            return {
                OUTPUT_PARAMETER: self._publish_ref(
                    result, parameters, context, folder=False
                )
            }
        if kind.name == "outputFolder":
            return {
                OUTPUT_PARAMETER: self._publish_ref(
                    result, parameters, context, folder=True
                )
            }
        if kind.name == "outputMultilayer":
            return {
                MULTI_OUTPUT_NAME: self._publish_layers(result, parameters, context)
            }
        return {OUTPUT_PARAMETER: result}

    def _destination_path(
        self, parameters: dict, context: QgsProcessingContext
    ) -> Path:
        destination = self.parameterAsFileOutput(parameters, OUTPUT_PARAMETER, context)
        if not destination:
            raise QgsProcessingException(f"{OUTPUT_PARAMETER} requires a destination")
        return Path(destination)

    def _copy_file(
        self, source: Path, parameters: dict, context: QgsProcessingContext
    ) -> str:
        """Copy one produced file to the destination the dialog chose."""
        destination = self._destination_path(parameters, context)
        shutil.copyfile(source, destination)
        return str(destination)

    def _publish_ref(
        self, ref: Any, parameters: dict, context: QgsProcessingContext, *, folder: bool
    ) -> str:
        """Publish the file or folder a produced ref names, never the ref's
        own borrowed path (decision-19: the destination is explicit)."""
        files = _files_of(self._bridge)
        if files is None:
            raise QgsProcessingException(
                "this host has no files service, so a produced ref cannot be published"
            )
        source = Path(files.resolve(ref, operation="read"))
        destination = self._destination_path(parameters, context)
        if folder:
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copyfile(source, destination)
        return str(destination)

    def _publish_layers(
        self, layers: Any, parameters: dict, context: QgsProcessingContext
    ) -> list[str]:
        """Write every produced layer into the chosen folder, one file each."""
        folder = self._destination_path(parameters, context)
        folder.mkdir(parents=True, exist_ok=True)
        published: list[str] = []
        for layer in layers:
            produced = self._bridge.layers._qgs_layer(layer.id)
            name = layer.name or produced.name() or "layer"
            target = folder / f"{name}.gpkg"
            number = 2
            while target.exists():
                target = folder / f"{name}-{number}.gpkg"
                number += 1
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = target.stem
            error, _new_name, message = QgsVectorFileWriter.writeAsVectorFormatV3(
                produced, str(target), context.transformContext(), options
            )
            if error:
                raise QgsProcessingException(
                    f"cannot write {target.name}: {message or 'the writer refused'}"
                )
            published.append(str(target))
        return published

    def _value(
        self,
        name: str,
        kind: str,
        parameters: dict,
        context: QgsProcessingContext,
        minted: list[str],
    ) -> Any:
        """Turn one Processing parameter value into the input's keyword value.

        A file or directory picked in the dialog is a native picker result, so
        it is granted through the host authority (decision-20) and the handler
        receives the ``FileRef``, never the path the dialog held.
        """
        if kind in ("file", "directory"):
            path = self.parameterAsFile(parameters, name, context)
            if not path:
                raise QgsProcessingException(f"{name} requires a {kind}")
            authority, binding = self._bridge.authority, self._bridge.binding
            if kind == "file":
                ref = authority.grant_file(binding, path, source="picker")
            else:
                ref = authority.grant_directory(binding, path, source="picker")
            minted.append(ref.id)
            return ref
        if kind == "field":
            return self.parameterAsString(parameters, name, context)
        if kind == "range":
            annotation = self._description.annotations[name]
            bounds = _marker(annotation, RangeParameter)
            if isinstance(bounds.minimum, int) and isinstance(bounds.maximum, int):
                return self.parameterAsInt(parameters, name, context)
            return self.parameterAsDouble(parameters, name, context)
        if kind == "colour":
            colour = _marker(self._description.annotations[name], ColourParameter)
            return _hex_rgba(
                self.parameterAsColor(parameters, name, context),
                alpha=colour is None or colour.alpha,
            )
        if kind == "enum":
            options = get_args(self._description.annotations[name])
            return options[self.parameterAsEnum(parameters, name, context)]
        if kind == LAYER_PARAMETER:
            # The SDK owns the layers it opened, so the picked layer is
            # re-opened through the same service the rest of the bridge uses -
            # the raster service when the input asked for a raster.
            wanted = (
                _marker(self._description.annotations[name], LayerParameter)
                or LayerParameter()
            ).kind
            if wanted == "raster":
                raster = self.parameterAsRasterLayer(parameters, name, context)
                if raster is None:
                    raise QgsProcessingException(f"{name} requires a raster layer")
                return _rasters_of(self._bridge).open_raster(Path(raster.source())).id
            if wanted == "any":
                # One parameter class lists both kinds (a MapLayer parameter), so
                # the picked layer's own type decides which service re-opens it.
                picked = self.parameterAsMapLayer(parameters, name, context)
                if picked is None:
                    raise QgsProcessingException(f"{name} requires a map layer")
                if picked.type() == Qgis.LayerType.Raster:
                    return (
                        _rasters_of(self._bridge).open_raster(Path(picked.source())).id
                    )
                return self._bridge.layers.open_vector(Path(picked.source())).id
            layer = self.parameterAsVectorLayer(parameters, name, context)
            if layer is None:
                raise QgsProcessingException(f"{name} requires a vector layer")
            return self._bridge.layers.open_vector(Path(layer.source())).id
        if kind == METRES_PARAMETER:
            return self.parameterAsDouble(parameters, name, context)
        if kind == CRS_PARAMETER:
            return self.parameterAsCrs(parameters, name, context).authid()
        if kind == "string":
            return self.parameterAsString(parameters, name, context)
        if kind == "integer":
            return self.parameterAsInt(parameters, name, context)
        if kind == "number":
            return self.parameterAsDouble(parameters, name, context)
        return self.parameterAsBool(parameters, name, context)

    def _copy_to_sink(
        self, layer_id: str, parameters: dict, context: QgsProcessingContext
    ) -> str:
        """Copy the produced layer's features into the destination QGIS asked for."""
        produced = self._bridge.layers._qgs_layer(layer_id)
        sink, destination = self.parameterAsSink(
            parameters,
            OUTPUT_PARAMETER,
            context,
            produced.fields(),
            produced.wkbType(),
            produced.crs(),
        )
        for feature in produced.getFeatures():
            copy = QgsFeature(produced.fields())
            copy.setGeometry(feature.geometry())
            copy.setAttributes(feature.attributes())
            sink.addFeature(copy, QgsFeatureSink.FastInsert)
        return destination


class NativeProcessingProvider(QgsProcessingProvider):
    """A ``QgsProcessingProvider`` backed by an SDK ``Provider``.

    Holds the services the bridge needs. They are the caller's runtime objects on
    purpose: the layers an algorithm opens, the temporary outputs it writes and
    the scope that owns them stay the plugin's, not this adapter's.
    """

    def __init__(
        self,
        provider: Provider,
        *,
        layers: NativeLayers,
        algorithms: NativeAlgorithms,
        project: NativeProject,
        scope: ResourceScope,
        authority: HostAuthority | None = None,
        rasters: NativeRasters | None = None,
    ) -> None:
        super().__init__()
        self._provider = provider
        self.layers = layers
        #: The raster service a raster ``LayerInput`` re-opens through
        #: (TASK-87). Without one, a raster input on an algorithm refuses by
        #: name - the dialog would otherwise accept a layer nothing can read.
        self.rasters = rasters
        # Not ``self.algorithms``: that is ``QgsProcessingProvider.algorithms()``,
        # which the registry calls to enumerate what this provider offers.
        self.algorithm_service = algorithms
        self.project = project
        self.scope = scope
        #: Mints the refs for files a Processing dialog picked; a host that
        #: shares one authority with its views passes it in, so the refs a
        #: handler receives resolve wherever the runtime resolves refs.
        self.authority = authority if authority is not None else HostAuthority()
        self.binding = ViewBinding(
            view_id=f"processing:{provider.id}",
            origin="qgis://processing",
            generation=0,
        )

    @property
    def provider_id(self) -> str:
        return self._provider.id

    def function_for(self, algorithm_id: str) -> Any:
        """Return the declared function behind one bridge algorithm."""
        return self._provider.function_for(algorithm_id)

    def id(self) -> str:
        return self._provider.id

    def name(self) -> str:
        return self._provider.title

    def unregister(self) -> None:
        """Remove this provider and every algorithm it added from the registry.

        ``QgsProcessingProvider`` has no public removal method in QGIS 4.2, so the
        registry is the one that owns removal; exposing it here keeps the plugin
        from having to import ``QgsApplication`` just to unload itself.
        """
        QgsApplication.processingRegistry().removeProvider(self)

    def loadAlgorithms(self) -> None:
        for description in self._provider.describe().algorithms:
            self.addAlgorithm(_BridgeAlgorithm(self, description))


class NativeProcessing:
    """``ctx.processing`` for a QGIS host: the plugin's providers in the registry.

    Holds the services every registered bridge needs. They are the plugin's
    runtime objects on purpose: the layers an algorithm opens, the temporary
    outputs it writes and the scope that owns them stay the plugin's.
    """

    def __init__(
        self,
        *,
        layers: NativeLayers,
        algorithms: NativeAlgorithms,
        project: NativeProject,
        scope: ResourceScope,
        authority: HostAuthority | None = None,
        rasters: NativeRasters | None = None,
    ) -> None:
        self._layers = layers
        self._algorithms = algorithms
        self._project = project
        self._scope = scope
        self._authority = authority if authority is not None else HostAuthority()
        self._rasters = rasters

    def register_provider(self, provider: Provider) -> NativeProcessingProvider:
        """Advertise ``provider``; ``unregister()`` on the result removes it."""
        self._scope.ensure_open()
        return register_provider(
            provider,
            layers=self._layers,
            algorithms=self._algorithms,
            project=self._project,
            scope=self._scope,
            authority=self._authority,
            rasters=self._rasters,
        )


def register_provider(
    provider: Provider,
    *,
    layers: NativeLayers,
    algorithms: NativeAlgorithms,
    project: NativeProject,
    scope: ResourceScope,
    authority: HostAuthority | None = None,
    rasters: NativeRasters | None = None,
) -> NativeProcessingProvider:
    """Register ``provider`` with QGIS and return the adapter that owns it.

    The adapter's own implementation behind :class:`NativeProcessing`; a plugin
    lists ``providers = [...]`` and lets the runtime call this (decision-42).
    The returned object is what ``QgsApplication.processingRegistry()`` now
    holds; calling ``unregister()`` on it removes every algorithm it added.
    """
    # The registry lives inside the Processing framework, so loading it is part
    # of registering: afterwards `processing.run` works for the caller too.
    _processing()
    bridge = NativeProcessingProvider(
        provider,
        layers=layers,
        algorithms=algorithms,
        project=project,
        scope=scope,
        authority=authority,
        rasters=rasters,
    )
    if not QgsApplication.processingRegistry().addProvider(bridge):
        raise QgisSdkDeclarationError(
            f"provider {provider.id!r} is already registered with QGIS"
        )
    return bridge
