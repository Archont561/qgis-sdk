"""The catalogue's feedback components (decision-55 point 3).

``JobProgress`` follows one :class:`~qgis_sdk.jobs.JobHandle` - its
fraction, its outcome, a Cancel button; ``LogView`` shows the records the
plugin writes through ``ctx.log`` (decision-63); ``ResultTable`` lists rows
of plain mappings under named columns and remembers which one is selected.
Like the inputs they are state first: a pure test binds a handle, writes a
record or sets rows and reads the same state the widget would show.
"""

from __future__ import annotations

from ._feedback import JobProgress, LogView
from ._result_table import ResultTable

__all__ = ["JobProgress", "LogView", "ResultTable"]
