"""Expected failures that callers can distinguish without importing QGIS."""

from dataclasses import dataclass


class QgisSdkError(Exception):
    """Base class for expected SDK errors; adapters may translate its code."""

    code = "sdk_error"


class QgisSdkScopeClosedError(QgisSdkError):
    """An operation attempted to use an already disposed owner scope."""

    code = "scope_closed"

    def __init__(self) -> None:
        super().__init__("This resource scope has been disposed")


class QgisSdkUnsupportedCapabilityError(QgisSdkError):
    """The selected runtime does not offer an explicitly requested capability.

    ``reason`` is set when the capability exists elsewhere in the same runtime
    but not *here* - a worker thread, for example, which must not touch the
    project the driving thread owns (decision-65). The message then says why
    instead of only that the host lacks the service.

    Args:
        capability: The capability the caller asked for, by name.
        reason: Why it is unavailable here, when the host can say.
    """

    code = "unsupported_capability"

    def __init__(self, capability: str, reason: str | None = None) -> None:
        self.capability = capability
        self.reason = reason
        message = f"Capability {capability!r} is unavailable in this runtime"
        if reason is not None:
            message = f"Capability {capability!r} is unavailable here: {reason}"
        super().__init__(message)


class QgisSdkOptionalDependencyError(QgisSdkError):
    """An explicitly selected adapter needs an administrator-provisioned package.

    Args:
        dependency: The package that is missing.
        installation_hint: How an administrator installs it.
    """

    code = "optional_dependency_unavailable"

    def __init__(self, dependency: str, installation_hint: str) -> None:
        self.dependency = dependency
        self.installation_hint = installation_hint
        super().__init__(
            f"Optional dependency {dependency!r} is unavailable. {installation_hint}"
        )


@dataclass(frozen=True, slots=True)
class QgisSdkValidationIssue:
    """Safe, structured location and category for a rejected contract value.

    Attributes:
        path: Where in the rejected value the problem is, as keys and indexes.
        code: The category of the problem, such as ``missing``.
    """

    path: tuple[str | int, ...]
    code: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible issue without including the rejected value."""
        return {"path": list(self.path), "code": self.code}
