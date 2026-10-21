"""QGIS-free value and error types shared by the SDK layers."""

from .errors import (
    QgisSdkContractValidationError,
    QgisSdkError,
    QgisSdkJobCancelledError,
    QgisSdkOptionalDependencyError,
    QgisSdkSchedulingBlockedError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
    QgisSdkValidationIssue,
)

__all__ = [
    "QgisSdkContractValidationError",
    "QgisSdkError",
    "QgisSdkJobCancelledError",
    "QgisSdkOptionalDependencyError",
    "QgisSdkSchedulingBlockedError",
    "QgisSdkScopeClosedError",
    "QgisSdkUnsupportedCapabilityError",
    "QgisSdkValidationIssue",
]
