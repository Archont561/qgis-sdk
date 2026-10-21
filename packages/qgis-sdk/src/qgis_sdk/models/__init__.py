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
from .limits import MAX_SAFE_INTEGER

__all__ = [
    "MAX_SAFE_INTEGER",
    "QgisSdkContractValidationError",
    "QgisSdkError",
    "QgisSdkJobCancelledError",
    "QgisSdkOptionalDependencyError",
    "QgisSdkSchedulingBlockedError",
    "QgisSdkScopeClosedError",
    "QgisSdkUnsupportedCapabilityError",
    "QgisSdkValidationIssue",
]
