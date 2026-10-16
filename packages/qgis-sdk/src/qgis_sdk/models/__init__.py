"""QGIS-free value and error types shared by the SDK layers."""

from .errors import (
    QgisSdkContractValidationError,
    QgisSdkError,
    QgisSdkOptionalDependencyError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
    QgisSdkValidationIssue,
)

__all__ = [
    "QgisSdkContractValidationError",
    "QgisSdkError",
    "QgisSdkOptionalDependencyError",
    "QgisSdkScopeClosedError",
    "QgisSdkUnsupportedCapabilityError",
    "QgisSdkValidationIssue",
]
