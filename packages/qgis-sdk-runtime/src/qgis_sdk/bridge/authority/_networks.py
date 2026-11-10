"""Network grants: one per view, in the generation it was given in."""

from __future__ import annotations

from dataclasses import dataclass, field

from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.models import QgisSdkGrantRefusedError
from qgis_sdk.network.grants import NetworkGrant

from ._grants import _NetworkGrant


@dataclass
class _NetworkGrants:
    """What each view may reach, keyed by the view, replaced when it is granted again."""

    items: dict[str, _NetworkGrant] = field(default_factory=dict)

    def grant(self, binding: ViewBinding, grant: NetworkGrant) -> None:
        """Give ``binding``'s view ``grant``, replacing any earlier one."""
        self.items[binding.view_id] = _NetworkGrant(grant, binding.generation)

    def get(self, binding: ViewBinding) -> NetworkGrant | None:
        """The view's grant in this generation, or ``None``."""
        granted = self.items.get(binding.view_id)
        if granted is None or granted.generation != binding.generation:
            return None
        return granted.grant

    def require(self, binding: ViewBinding) -> NetworkGrant:
        """The view's grant, or the refusal a network operation reports."""
        grant = self.get(binding)
        if grant is None:
            raise QgisSdkGrantRefusedError("this view holds no network grant")
        return grant

    def revoke(self, binding: ViewBinding) -> bool:
        """Withdraw the view's grant; ``True`` when there was one to withdraw."""
        return self.items.pop(binding.view_id, None) is not None

    def release_view(self, view_id: str) -> None:
        """Forget the view's grant; it is granted nothing until it asks again."""
        self.items.pop(view_id, None)

    def prune(self, generation: int) -> int:
        """Drop the grants of every generation before ``generation``."""
        stale = [
            view_id
            for view_id, granted in self.items.items()
            if granted.generation < generation
        ]
        for view_id in stale:
            del self.items[view_id]
        return len(stale)
