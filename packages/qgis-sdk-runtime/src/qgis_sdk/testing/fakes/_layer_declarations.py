"""The declaration half of :class:`FakeLayers`: which datasets a test provides.

Declaring is setup, not part of the ``Layers`` contract - a host never asks a
layer backend what it will open - so it lives in one mixin the fake composes.
"""

from __future__ import annotations

from qgis_sdk.models import AnnotationLayerInfo

from ._algorithms import other_dataset, vector_dataset
from ._declarations import OtherLayerDeclaration, VectorLayerDeclaration

__all__ = ["LayerDeclarations"]


class LayerDeclarations:
    """What the fake answers with, declared by the test."""

    def register(self, declaration: VectorLayerDeclaration) -> None:
        """Declare a vector dataset; ``dataset_path`` models a container URI.

        Args:
            declaration: The vector dataset the fake answers for.
        """
        self._datasets[str(declaration.source)] = vector_dataset(declaration)

    def register_layer(self, declaration: OtherLayerDeclaration) -> None:
        """Declare a mesh, point cloud, vector tile or tiled scene dataset.

        Args:
            declaration: The dataset the fake answers for.
        """
        self._datasets[str(declaration.source)] = other_dataset(declaration)

    def register_annotation(
        self, name: str, *, item_count: int = 0, crs: str | None = None
    ) -> None:
        """Declare what opening the annotation layer ``name`` answers.

        An annotation layer has no dataset to open, so what a test declares is
        the layer a project already holds - its items and its CRS - and opening
        an undeclared name creates an empty one.

        Args:
            name: The dataset path the annotation layer is opened by.
            item_count: How many annotation items it reports.
            crs: The authority code its items are placed in.
        """
        AnnotationLayerInfo(id="declared", name=name, item_count=item_count, crs=crs)
        self._annotations[name] = AnnotationLayerInfo(
            id="declared", name=name, item_count=item_count, crs=crs
        )
