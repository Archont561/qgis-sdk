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
