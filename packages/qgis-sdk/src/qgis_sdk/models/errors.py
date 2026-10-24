"""Expected failures that callers can distinguish without importing QGIS."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal


class QgisSdkError(Exception):
    """Base class for expected SDK errors; adapters may translate its code."""

    code = "sdk_error"


class QgisSdkScopeClosedError(QgisSdkError):
    """An operation attempted to use an already disposed owner scope."""

    code = "scope_closed"

    def __init__(self) -> None:
        super().__init__("This resource scope has been disposed")


class QgisSdkUnsupportedCapabilityError(QgisSdkError):
    """The selected runtime does not offer an explicitly requested capability."""

    code = "unsupported_capability"

    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(f"Capability {capability!r} is unavailable in this runtime")


class QgisSdkOptionalDependencyError(QgisSdkError):
    """An explicitly selected adapter needs an administrator-provisioned package."""

    code = "optional_dependency_unavailable"

    def __init__(self, dependency: str, installation_hint: str) -> None:
        self.dependency = dependency
        self.installation_hint = installation_hint
        super().__init__(
            f"Optional dependency {dependency!r} is unavailable. {installation_hint}"
        )


class QgisSdkLayerNotFoundError(QgisSdkError):
    """No layer or dataset with this identifier exists in the runtime.

    The identifier is either a layer id or a dataset location, whichever the
    caller used, so the message never claims to know which kind was meant.
    """

    code = "layer_not_found"

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"No layer {identifier!r} is available in this runtime")


class QgisSdkStyleIncompatibleError(QgisSdkError):
    """A packaged style cannot be applied to the target layer.

    Reasons are short, user-readable statements about the mismatch that was
    detected, never the rejected layer object.
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


@dataclass(frozen=True, slots=True)
class QgisSdkValidationIssue:
    """Safe, structured location and category for a rejected contract value."""

    path: tuple[str | int, ...]
    code: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible issue without including the rejected value."""
        return {"path": list(self.path), "code": self.code}


class QgisSdkContractValidationError(QgisSdkError):
    """A request or result did not satisfy its declared wire contract."""

    code = "contract_validation_failed"

    def __init__(
        self,
        direction: Literal["request", "result"],
        issues: Iterable[QgisSdkValidationIssue],
    ) -> None:
        self.direction = direction
        self.issues = tuple(issues)
        super().__init__(f"{direction.title()} contract validation failed")

    def as_dict(self) -> dict[str, object]:
        """Return stable error metadata without raw input or validator internals."""
        return {
            "code": self.code,
            "direction": self.direction,
            "issues": [issue.as_dict() for issue in self.issues],
        }


class QgisSdkJobCancelledError(QgisSdkError):
    """Cancellation reached a job at its next suspension point.

    The scheduler throws this into the coroutine so author ``finally`` blocks
    run; suppressing it lets the work continue, because cancellation is
    cooperative and never proof that the worker stopped.
    """

    code = "job_cancelled"

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        super().__init__(f"Job {job_id} was cancelled at its next suspension point")


class QgisSdkSchedulingBlockedError(QgisSdkError):
    """The scheduler refused a submission or in-process replacement.

    Work that cannot reach a safe point is named as the blocker: replacing the
    runtime anyway would delete native resources under a running worker.
    """

    code = "scheduling_blocked"

    def __init__(self, blockers: Iterable[str]) -> None:
        self.blockers = tuple(blockers)
        listed = "; ".join(self.blockers)
        super().__init__(f"Scheduling is blocked: {listed}")
