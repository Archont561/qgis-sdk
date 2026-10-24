"""Pure capability contracts; implementations are injected by runtime adapters."""

from .contracts import Cancellation, DesktopAccess, Notifications, Progress, ViewControl
from .layers import Layers
from .project import Project
from .settings import Settings
from .styles import Styles

__all__ = [
    "Cancellation",
    "DesktopAccess",
    "Layers",
    "Notifications",
    "Progress",
    "Project",
    "Settings",
    "Styles",
    "ViewControl",
]
