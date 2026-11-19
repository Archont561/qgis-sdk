"""Errors from a Processing run: refused, missing, failed or cancelled.

An algorithm's request is validated against the registry's own description
before any data is read, so a refusal here costs nothing and names every reason
at once.
"""

from __future__ import annotations

from collections.abc import Iterable

from ._base import QgisSdkError


class QgisSdkAlgorithmRejectedError(QgisSdkError):
    """An algorithm request was refused before it could touch any data.

    ``reasons`` are short statements about what made the request unsafe or
    ambiguous - an unspecified or geographic working CRS, units that are not
    metres, a distance that is not positive. They never include the rejected
    values themselves, so the error can be logged as-is.

    Args:
        request: The request that was refused, as the caller described it.
        reasons: What made it unsafe or ambiguous, one sentence each.
    """

    code = "algorithm_rejected"

    def __init__(self, request: str, reasons: Iterable[str]) -> None:
        self.request = request
        self.reasons = tuple(reasons)
        listed = "; ".join(self.reasons)
        super().__init__(f"Algorithm request {request!r} was refused: {listed}")


class QgisSdkAlgorithmNotFoundError(QgisSdkError):
    """No algorithm with this id is registered on the host (or in the catalogue).

    Args:
        algorithm_id: The ``provider:name`` id that is not registered.
    """

    code = "algorithm_not_found"

    def __init__(self, algorithm_id: str) -> None:
        self.algorithm_id = algorithm_id
        super().__init__(f"Algorithm {algorithm_id!r} is not registered")


class QgisSdkAlgorithmFailedError(QgisSdkError):
    """Processing ran the algorithm and it failed.

    ``detail`` describes the failure. SDK-owned staging is cleaned up on a
    best-effort basis; external provider side effects cannot be rolled back.

    Args:
        algorithm_id: The algorithm that ran.
        detail: What the provider reported about the failure.
    """

    code = "algorithm_failed"

    def __init__(self, algorithm_id: str, detail: str) -> None:
        self.algorithm_id = algorithm_id
        self.detail = detail
        super().__init__(f"Algorithm {algorithm_id!r} failed: {detail}")


class QgisSdkAlgorithmCancelledError(QgisSdkError):
    """Cancellation was observed at an algorithm phase boundary.

    Cancellation is cooperative: this says the request was not run (or its
    result was not accepted), never that a native operation stopped mid-flight.

    Args:
        algorithm_id: The algorithm whose request was cancelled.
    """

    code = "algorithm_cancelled"

    def __init__(self, algorithm_id: str) -> None:
        self.algorithm_id = algorithm_id
        super().__init__(f"Algorithm {algorithm_id!r} was cancelled")
