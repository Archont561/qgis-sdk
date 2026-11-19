"""Errors for content that was supplied, rendered or written, and failed.

A style document, a project file and an export are all values a caller hands
over; these are the refusals they can hear back, with every reason at once and
nothing written when the answer is a refusal.
"""

from __future__ import annotations

from collections.abc import Iterable

from ._base import QgisSdkError


class QgisSdkStyleIncompatibleError(QgisSdkError):
    """A packaged style cannot be applied to the target layer.

    Reasons are short, user-readable statements about the mismatch that was
    detected, never the rejected layer object.

    Args:
        layer_id: The layer the style was meant for.
        style: The packaged style that was applied.
        reasons: Why the two do not fit, one sentence each.
    """

    code = "style_incompatible"

    def __init__(
        self,
        layer_id: str,
        style: str,
        reasons: Iterable[str],
    ) -> None:
        self.layer_id = layer_id
        self.style = style
        self.reasons = tuple(reasons)
        listed = "; ".join(self.reasons)
        super().__init__(
            f"Style {style!r} is incompatible with layer {layer_id!r}: {listed}"
        )


class QgisSdkStyleTextError(QgisSdkError):
    """A style document could not be read in the dialect the caller named.

    QML and SLD are two different documents, and a host that guessed which one it
    was handed would fail somewhere inside QGIS with a message about an XML node
    nobody asked for. The caller says which dialect its text is; a document that
    is not one raises this, with the format and the reason the reader gave.

    Args:
        format: The dialect the text was expected in: ``QML`` or ``SLD``.
        detail: The reader's reason for refusing it.
    """

    code = "style_text_rejected"

    def __init__(self, format: str, detail: str) -> None:
        self.format = format
        self.detail = detail
        super().__init__(
            f"The style text is not a readable {format} document: {detail}"
        )


class QgisSdkProjectFileError(QgisSdkError):
    """A project file could not be read, written or saved.

    ``detail`` is the host's own message when it gave one. A failed write leaves
    the previous file in place: the project is written to a staged path and
    replaces its destination only after the writer finished.

    Args:
        path: The project file that could not be used.
        detail: The host's own message, when it gave one.
    """

    code = "project_file_error"

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Project file {path!r}: {detail}")


class QgisSdkExportRefusedError(QgisSdkError):
    """An export cannot start as requested: the destination fails a precondition.

    Nothing has been written when this is raised. Every reason is reported at
    once - an unknown format, a missing directory and an existing file without
    ``overwrite`` are three separate statements, not three round trips.

    Args:
        destination: The destination that was refused, as the caller named it.
        reasons: Every precondition the request failed, one sentence each.
    """

    code = "export_refused"

    def __init__(self, destination: str, reasons: Iterable[str]) -> None:
        self.destination = destination
        self.reasons = tuple(reasons)
        listed = "; ".join(self.reasons)
        super().__init__(f"Export to {destination!r} refused: {listed}")


class QgisSdkExportFailedError(QgisSdkError):
    """The writer failed after the export started; the partial file is gone.

    ``detail`` is the writer's own message. The destination was either never
    created or, with ``overwrite``, still holds its previous content: the new
    file is committed only after the writer finished.

    Args:
        destination: The destination the writer was writing.
        detail: The writer's own message.
    """

    code = "export_failed"

    def __init__(self, destination: str, detail: str) -> None:
        self.destination = destination
        self.detail = detail
        super().__init__(f"Export to {destination!r} failed: {detail}")


class QgisSdkPackagedResourceError(QgisSdkError):
    """A resource the package must ship is missing or unusable.

    This is a packaging defect, not a caller mistake: the style was requested by
    a known identifier and the layer was already found compatible.

    Args:
        style: The packaged style that could not be used.
        detail: What was wrong with it.
    """

    code = "packaged_resource_unavailable"

    def __init__(self, style: str, detail: str) -> None:
        self.style = style
        self.detail = detail
        super().__init__(f"Packaged style {style!r} could not be used: {detail}")
