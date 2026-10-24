"""QGIS-free value and error types shared by the SDK layers."""

from .errors import (
    QgisSdkContractValidationError,
    QgisSdkError,
    QgisSdkJobCancelledError,
    QgisSdkLayerNotFoundError,
    QgisSdkOptionalDependencyError,
    QgisSdkSchedulingBlockedError,
    QgisSdkScopeClosedError,
    QgisSdkStyleIncompatibleError,
    QgisSdkUnsupportedCapabilityError,
    QgisSdkValidationIssue,
)
from .layers import GeometryType, VectorLayerInfo
from .limits import MAX_SAFE_INTEGER

__all__ = [
    "MAX_SAFE_INTEGER",
    "GeometryType",
    "QgisSdkContractValidationError",
    "QgisSdkError",
    "QgisSdkJobCancelledError",
    "QgisSdkLayerNotFoundError",
    "QgisSdkOptionalDependencyError",
    "QgisSdkSchedulingBlockedError",
    "QgisSdkScopeClosedError",
    "QgisSdkStyleIncompatibleError",
    "QgisSdkUnsupportedCapabilityError",
    "QgisSdkValidationIssue",
    "VectorLayerInfo",
]
