"""Generation-safe plugin reload inside QGIS Desktop for ``qgis-sdk dev``.

The policy is decision-15 and decision-21, in this order for every reload:

1. **Preflight** the next revision without touching the running one: every
   module compiles and ``check_project`` finds nothing QGIS would refuse
   (syntax, metadata, project shape). Architecture findings only warn.
2. **Quiesce** the running revision through its own runtime
   (``PluginRuntime.quiesce``): owned work is cancelled and given a bounded
   time to reach a safe point. A refusal names the blockers, the revision
   is resumed and left exactly as it was, and the message says a restart is
   the way out - no thread is killed and nothing unsaved is discarded.
3. **Replace**: unload, then load and start the source again. A failure
   after teardown cannot be undone, so the plugin is disabled visibly
   (message bar + terminal) until the next reload succeeds.

Requests are serialised and coalesced: a reload while one is in flight is
folded into exactly one follow-up, and a host timer debounces bursts from
the editor or the watcher. Each attempt gets a generation number so
messages and reports can be tied to the attempt they belong to. Frontend
changes are not this module's business: Vite's HMR owns them.

Everything here is plain Python so it can be driven without QGIS; the Qt
and ``qgis.utils`` glue is :mod:`.bootstrap`, which the ``qgis --code``
probe calls.
"""

from __future__ import annotations

from ._coordinator import ReloadCoordinator
from ._preflight import preflight
from ._types import (
    ADVISORY_RULES,
    DEBOUNCE_MS,
    PROJECT_RULES,
    QUIESCE_SECONDS,
    UNWATCHED,
    WATCH_INTERVAL_MS,
    NotifyLevel,
    Outcome,
    PluginHost,
    ReloadReport,
)
from ._watcher import SourceWatcher

__all__ = [
    "ADVISORY_RULES",
    "DEBOUNCE_MS",
    "PROJECT_RULES",
    "QUIESCE_SECONDS",
    "UNWATCHED",
    "WATCH_INTERVAL_MS",
    "NotifyLevel",
    "Outcome",
    "PluginHost",
    "ReloadCoordinator",
    "ReloadReport",
    "SourceWatcher",
    "preflight",
]
