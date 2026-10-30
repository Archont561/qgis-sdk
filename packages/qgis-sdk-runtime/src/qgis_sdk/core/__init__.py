"""Runtime-independent composition of author-facing contexts and lifetimes."""

from .contexts import (
    GUI_BOUND_CAPABILITIES,
    AlgorithmContext,
    JobContext,
    PluginContext,
    UiContext,
    WorkerContext,
)
from .runtime import (
    PluginRuntime,
    PluginRuntimeState,
    QgisSdkPluginLifecycleError,
)
from .scheduling import (
    Handoff,
    Job,
    JobState,
    QuiesceOutcome,
    StepScheduler,
    Yield,
)
from .scope import ResourceScope

__all__ = [
    "GUI_BOUND_CAPABILITIES",
    "AlgorithmContext",
    "Handoff",
    "Job",
    "JobContext",
    "JobState",
    "PluginContext",
    "PluginRuntime",
    "PluginRuntimeState",
    "QgisSdkPluginLifecycleError",
    "QuiesceOutcome",
    "ResourceScope",
    "StepScheduler",
    "UiContext",
    "WorkerContext",
    "Yield",
]
