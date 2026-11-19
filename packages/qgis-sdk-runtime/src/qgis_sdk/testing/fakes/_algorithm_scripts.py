"""The setup half of :class:`FakeAlgorithms`: what the next run answers.

Scripting is not part of the ``Algorithms`` contract - a host never asks an
algorithm backend what it will produce - so it lives here, in one mixin the
fake composes, rather than in the protocol-shaped class beside it.
"""

from __future__ import annotations

from qgis_sdk.models import FileRef

from ._declarations import (
    DeclaredOutput,
    ScriptedModelOutputs,
    ScriptedOutputs,
    VectorLayerDeclaration,
)

__all__ = ["AlgorithmScripts"]


class AlgorithmScripts:
    """What each algorithm answers with, declared by the test."""

    def declare_output(self, output: DeclaredOutput) -> None:
        """Declare what a request type produces; setup, not part of the contract.

        Args:
            output: What the request type produces.
        """
        self._layers.register(
            VectorLayerDeclaration(
                output.source,
                name=output.name,
                geometry_type=output.geometry_type,
                field_names=output.field_names,
                crs=output.crs,
            )
        )
        self._outputs[output.request_type] = output.source

    def script_run(
        self,
        algorithm_id: str,
        outputs: ScriptedOutputs,
        *,
        repeat: bool = True,
    ) -> None:
        """Declare what the next ``run`` of ``algorithm_id`` produces.

        ``outputs`` maps output names to values, or is a callable taking the
        :class:`AlgorithmRun` and returning that mapping. A ``Path`` under a
        vector output is opened through the fake layers (register it first);
        a ``Path`` under a file output is granted through ``files`` and comes
        back as a ``FileRef``; anything else is returned as given. With
        ``repeat=False`` the answer is consumed by one run.

        Args:
            algorithm_id: The algorithm the next ``run`` calls.
            outputs: The output values to answer with.
            repeat: Whether the script answers every call, not just the next.
        """
        self._scripted.setdefault(algorithm_id, []).append((outputs, repeat))

    def script_run_model(
        self,
        model: FileRef,
        outputs: ScriptedModelOutputs,
        *,
        repeat: bool = True,
    ) -> None:
        """Declare what the next ``run_model`` of ``model`` produces.

        A model has no registry entry to script against, so the answer is
        keyed by the ref's id and the values are the final ones - owned
        :class:`VectorLayerInfo`, :class:`FileRef` objects or scalars, exactly
        the shapes :class:`RunResult` describes. A callable takes the ref and
        the params of the run. With ``repeat=False`` the answer is consumed by
        one run.

        Args:
            model: The model ref the next ``run_model`` calls.
            outputs: The output values to answer with.
            repeat: Whether the script answers every call, not just the next.
        """
        self._scripted_models.setdefault(model.id, []).append((outputs, repeat))
