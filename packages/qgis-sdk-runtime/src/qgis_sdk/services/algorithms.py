"""One execution capability: run an operation into a new, owned output."""

from __future__ import annotations

from typing import Protocol

from qgis_sdk.models import AlgorithmRequest, VectorLayerInfo


class Algorithms(Protocol):
    """Run one registered operation and return the layer it produced.

    The contract is deliberately narrow because every guarantee here is one
    decision-19 makes about destructive workflows:

    * ``execute`` never edits the source. It writes a new output and opens that
      output as a layer this runtime owns, so a caller that later styles or
      discards it is not touching the dataset it started from.
    * A failed execution leaves no partial output behind. Implementations
      remove what they wrote before re-raising, so a caller never has to know
      where the temporary file would have been.
    * The output is a separate layer, not a replacement: adding it to the
      project is the caller's decision and happens only after success.

    Requests are the typed models in ``qgis_sdk.models``. An unknown or
    undeclarable request raises ``QgisSdkAlgorithmRejectedError`` before any
    data is read, and an unknown layer raises ``QgisSdkLayerNotFoundError``.

    Requiring a *projected* working CRS is implemented by the native backend: it
    has the CRS database needed to tell projected from geographic and to check
    that the units are metres. The in-memory double refuses only what pure code
    can decide (an unspecified CRS), so do not read parity of that check into
    the fake.
    """

    def execute(self, request: AlgorithmRequest) -> VectorLayerInfo:
        """Run ``request`` into a new output and return its layer description."""
        ...
