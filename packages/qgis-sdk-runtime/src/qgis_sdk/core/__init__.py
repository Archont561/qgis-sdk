"""Runtime-independent composition of author-facing contexts and lifetimes."""

from .contexts import (
    GUI_BOUND_CAPABILITIES,
    AlgorithmContext,
    AlgorithmServices,
    JobContext,
    JobServices,
    PluginContext,
    PluginServices,
    UiContext,
    UiServices,
    WorkerContext,
)
from .host import Host
from .loops import LoopRegistry, LoopState, NamedLoop
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
    "AlgorithmServices",
    "Handoff",
    "Host",
    "Job",
    "JobContext",
    "JobServices",
    "JobState",
    "LoopRegistry",
    "LoopState",
    "NamedLoop",
    "PluginContext",
    "PluginRuntime",
    "PluginRuntimeState",
    "PluginServices",
    "QgisSdkPluginLifecycleError",
    "QuiesceOutcome",
    "ResourceScope",
    "StepScheduler",
    "UiContext",
    "UiServices",
    "WorkerContext",
    "Yield",
]
