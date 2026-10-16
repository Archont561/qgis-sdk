"""Pure capability contracts; implementations are injected by runtime adapters."""

from .contracts import Cancellation, DesktopAccess, Notifications, Progress, ViewControl

__all__ = ["Cancellation", "DesktopAccess", "Notifications", "Progress", "ViewControl"]
