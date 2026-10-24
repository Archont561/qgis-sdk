"""Expose a ``Provider`` as a QGIS Processing provider.

``register_provider`` takes the same object a plugin already declares its
algorithms on and makes it visible where QGIS users look for algorithms: the
Processing toolbox, ``processing.run("provider:algorithm", ...)``, the modeler and
batch mode. Nothing about an algorithm class changes - the bridge builds the
``QgsProcessingAlgorithm`` around it.

Two decisions worth reading before the code:

**Parameters come from the request dataclass.** Every field was already mapped to
a parameter kind when the provider was declared (``qgis_sdk.providers``), so this
module only has to translate a kind into a ``QgsProcessingParameter`` and the
widget value back into the field. A field that could not be mapped never reached
here, which is why there is no fallback widget below.

**The output is copied into a sink.** The operation writes a new layer through the
SDK; the bridge then copies its features into whatever destination the user chose
in the Processing dialog. That keeps decision-19's "explicit destination" and
leaves the produced temporary file untouched for the caller's own cleanup.

``FlagNoThreading`` is deliberate: this library has not qualified running these
adapters on a Processing worker thread, so the bridge tells QGIS to execute on the
thread it was qualified on instead of claiming a safety it cannot show.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsProcessingProvider,
)

from qgis_sdk.algorithms import AlgorithmDescription, invoke
from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.providers import LAYER_PARAMETER, METRES_PARAMETER, Provider

from .algorithms import NativeAlgorithms, _processing
from .layers import NativeLayers
from .project import NativeProject

__all__ = ["NativeProcessingProvider", "register_provider"]

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


def _parameter(kind: str, name: str) -> Any:
    """Build the Processing parameter a declared kind deserves."""
    if kind == LAYER_PARAMETER:
        return QgsProcessingParameterVectorLayer(name, name)
    if kind == METRES_PARAMETER:
        return QgsProcessingParameterNumber(
            name,
            f"{name} (metres)",
            type=QgsProcessingParameterNumber.Double,
            minValue=0.0,
        )
    if kind == "crs":
        return QgsProcessingParameterCrs(name, name)
    if kind == "string":
        return QgsProcessingParameterString(name, name)
    if kind == "integer":
        return QgsProcessingParameterNumber(
            name, name, type=QgsProcessingParameterNumber.Integer
        )
    if kind == "number":
        return QgsProcessingParameterNumber(
            name, name, type=QgsProcessingParameterNumber.Double
        )
    if kind == "boolean":
        return QgsProcessingParameterBoolean(name, name)
    raise QgisSdkDeclarationError(f"unsupported parameter kind {kind!r}")


class _BridgeAlgorithm(QgsProcessingAlgorithm):
    """One registered algorithm, presented as a native Processing algorithm."""

    def __init__(self, bridge: NativeProcessingProvider, registered: Any) -> None:
        super().__init__()
        self._bridge = bridge
        self._registered = registered
        self._description: AlgorithmDescription = registered.description

    def name(self) -> str:
        return self._description.id

    def displayName(self) -> str:
        return self._description.title

    def group(self) -> str:
        return self._registered.group or ""

    def groupId(self) -> str:
        return self._registered.group or ""

    def shortHelpString(self) -> str:
        return (
            f"{self._description.title} (qgis-sdk provider {self._bridge.provider_id})"
        )

    def initAlgorithm(self, config: dict | None = None) -> None:
        for name, kind in self._registered.parameters:
            self.addParameter(_parameter(kind, name))
        self.addParameter(QgsProcessingParameterFeatureSink(OUTPUT_PARAMETER, "Output"))

    def flags(self) -> QgsProcessingAlgorithm.Flag:
        return QgsProcessingAlgorithm.FlagNoThreading

    def createInstance(self) -> _BridgeAlgorithm:
        return _BridgeAlgorithm(self._bridge, self._registered)

    def processAlgorithm(
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        """Run the author's algorithm and hand its output to the chosen sink."""
        values = {
            name: self._value(name, kind, parameters, context)
            for name, kind in self._registered.parameters
        }
        inputs = self._registered.description.inputs_type(**values)
        scope = self._bridge.scope.child()
        try:
            result = invoke(
                self._bridge.algorithm_class(self._description.id),
                inputs,
                algorithms=self._bridge.algorithms,
                project=self._bridge.project,
                scope=scope,
                progress=_FeedbackProgress(feedback),
                cancellation=_FeedbackCancellation(feedback),
                add_to_project=False,
            )
        finally:
            scope.close()
        return {
            OUTPUT_PARAMETER: self._copy_to_sink(result.output.id, parameters, context)
        }

    def _value(
        self, name: str, kind: str, parameters: dict, context: QgsProcessingContext
    ) -> Any:
        """Turn one Processing parameter value into the request field's value."""
        if kind == LAYER_PARAMETER:
            layer = self.parameterAsVectorLayer(parameters, name, context)
            if layer is None:
                raise QgsProcessingException(f"{name} requires a vector layer")
            # The SDK owns layers it opened, so the picked layer is re-opened
            # through the same service the rest of the bridge uses.
            return self._bridge.layers.open_vector(Path(layer.source())).id
        if kind == METRES_PARAMETER:
            return self.parameterAsDouble(parameters, name, context)
        if kind == "crs":
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
    ) -> None:
        super().__init__()
        self._provider = provider
        self.layers = layers
        self.algorithms = algorithms
        self.project = project
        self.scope = scope

    @property
    def provider_id(self) -> str:
        return self._provider.id

    def algorithm_class(self, algorithm_id: str) -> type:
        """Return the registered class behind one bridge algorithm."""
        return self._provider.class_for(algorithm_id)

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
        for registered in self._provider.describe().algorithms:
            self.addAlgorithm(_BridgeAlgorithm(self, registered))


def register_provider(
    provider: Provider,
    *,
    layers: NativeLayers,
    algorithms: NativeAlgorithms,
    project: NativeProject,
    scope: ResourceScope,
) -> NativeProcessingProvider:
    """Register ``provider`` with QGIS and return the adapter that owns it.

    The returned object is what ``QgsApplication.processingRegistry()`` now holds;
    calling ``unregister()`` on it removes every algorithm it added.
    """
    # The registry lives inside the Processing framework, so loading it is part
    # of registering: afterwards `processing.run` works for the caller too.
    _processing()
    bridge = NativeProcessingProvider(
        provider, layers=layers, algorithms=algorithms, project=project, scope=scope
    )
    if not QgsApplication.processingRegistry().addProvider(bridge):
        raise QgisSdkDeclarationError(
            f"provider {provider.id!r} is already registered with QGIS"
        )
    return bridge
