"""Runtime-independent composition of author-facing contexts and lifetimes."""

from .contexts import AlgorithmContext, JobContext, PluginContext, UiContext
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
    "Yield",
]
