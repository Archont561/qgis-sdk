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
this package only has to translate a kind into a ``QgsProcessingParameter`` and
the widget value back into the keyword. An input that could not be mapped never
reached here, which is why there is no fallback widget.

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

The split below follows what a run touches. `_tables` is the vocabulary - which
Processing class each kind names; `_parameters` and `_values` are the two
directions of one dialog, a declaration into a widget and a widget's value back
into a keyword; `_publish` is where a finished output lands; `_services` is the
record of runtime objects a provider borrows; `_algorithm` and `_provider` are
the two classes QGIS calls; `_service` is ``ctx.processing`` itself.
"""

from __future__ import annotations

from ._provider import NativeProcessingProvider
from ._service import NativeProcessing

__all__ = ["NativeProcessing", "NativeProcessingProvider"]
