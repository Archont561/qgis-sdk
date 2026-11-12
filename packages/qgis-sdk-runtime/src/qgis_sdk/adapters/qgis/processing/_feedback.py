"""What a Processing run tells the dialog: progress out, cancellation in."""

from __future__ import annotations

from qgis.core import QgsProcessingFeedback


class FeedbackProgress:
    """Forward an execution's fraction to the dialog's progress bar."""

    def __init__(self, feedback: QgsProcessingFeedback) -> None:
        self._feedback = feedback

    def report(self, fraction: float) -> None:
        self._feedback.setProgress(int(fraction * 100))


class FeedbackCancellation:
    """Read cancellation from the Processing feedback, not from a second source."""

    def __init__(self, feedback: QgsProcessingFeedback) -> None:
        self._feedback = feedback

    def is_cancelled(self) -> bool:
        return self._feedback.isCanceled()
