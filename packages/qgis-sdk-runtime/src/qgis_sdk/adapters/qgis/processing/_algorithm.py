"""One registered algorithm, presented as a native Processing algorithm.

The class is the toolbox's view of a function: it declares the dialog, runs the
function through ``invoke`` and hands the result to the publisher. What a run
touches - the widgets, the values, the destinations - lives in the modules
beside it, so this file is the shape QGIS calls rather than the work.
"""

from __future__ import annotations

from typing import Any

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
)

from qgis_sdk.algorithms import AlgorithmDescription, invoke
from qgis_sdk.core import AlgorithmContext, AlgorithmServices, ResourceScope
from qgis_sdk.models import output_kinds

from ._feedback import _FeedbackCancellation, _FeedbackProgress
from ._parameters import _parameter
from ._publish import _Run, published
from ._tables import (
    _DESTINATION_CLASSES,
    _OUTPUT_CLASSES,
    MULTI_OUTPUT_NAME,
    OUTPUT_PARAMETER,
)
from ._values import values_of


class _BridgeAlgorithm(QgsProcessingAlgorithm):
    """One registered algorithm, presented as a native Processing algorithm."""

    def __init__(self, bridge: Any, description: AlgorithmDescription) -> None:
        super().__init__()
        self._bridge = bridge
        self._description = description

    @property
    def bridge(self) -> Any:
        """The provider this algorithm belongs to, for the services a run needs."""
        return self._bridge

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
        """Declare the dialog: one widget per input, then where the result goes."""
        self._add_inputs()
        self._add_output()

    def _add_inputs(self) -> None:
        for name, kind in self._description.kinds.items():
            self.addParameter(
                _parameter(kind, name, self._description.annotations[name])
            )

    def _add_output(self) -> None:
        """Offer the destination the result kind writes to, and the output itself."""
        kind = output_kinds()[self._description.result_kind]
        destination = _DESTINATION_CLASSES.get(kind.name)
        if destination is not None:
            destination_class, options = destination
            # ``createOutput=False``: the automatic output a destination
            # parameter would add has the parameter's own type, which is wrong
            # where the result kind is an HTML report or several layers - the
            # declared output is the one true face.
            self.addParameter(
                destination_class(OUTPUT_PARAMETER, "Output", **options), False
            )
        named = (
            MULTI_OUTPUT_NAME if kind.name == "outputMultilayer" else OUTPUT_PARAMETER
        )
        self.addOutput(_OUTPUT_CLASSES[kind.processing](named, "Output"))

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
        values = values_of(self, self._description, parameters, context, minted)
        scope = self._bridge.scope.child()
        try:
            result = self._invoke(values, scope, feedback)
        finally:
            scope.close()
            # The refs minted for this run were the dialog's picker results;
            # they expire with the run, like a view's refs with the view.
            for ref_id in minted:
                self._bridge.authority.revoke(ref_id)
        run = _Run(self, self._bridge, result, parameters, context)
        return published(run, self._description.result_kind)

    def _invoke(
        self, values: dict, scope: ResourceScope, feedback: QgsProcessingFeedback
    ) -> Any:
        """Call the author's function through the same runner an action uses."""
        return invoke(
            self._bridge.function_for(self._description.id),
            AlgorithmContext(
                progress=_FeedbackProgress(feedback),
                cancellation=_FeedbackCancellation(feedback),
                scope=scope,
                services=AlgorithmServices(
                    algorithms=self._bridge.algorithm_service,
                    project=self._bridge.project,
                ),
            ),
            add_to_project=False,
            **values,
        )
