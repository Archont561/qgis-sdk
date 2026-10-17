"""Shared exceptions for the qgis-sdk-release tool."""

__all__ = ["QgisSdkReleaseError", "QgisSdkReleaseVersionError"]


class QgisSdkReleaseError(Exception):
    """Base error for every qgis-sdk-release failure."""


class QgisSdkReleaseVersionError(QgisSdkReleaseError, ValueError):
    """Raised when a version, tag, or prerelease suffix cannot be parsed."""
