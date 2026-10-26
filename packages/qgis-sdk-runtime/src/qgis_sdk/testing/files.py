"""``FakeFiles``: the real ``Files`` rule over a private authority."""

from __future__ import annotations

from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.core import ResourceScope
from qgis_sdk.files import FilesService


class FakeFiles(FilesService):
    """``ctx.files`` for a pure test: refuses exactly what a host refuses.

    There is no simpler rule to fake - a forged ref is unknown, a read ref
    does not write, a ref minted for another owner does not resolve here -
    so the fake is :class:`~qgis_sdk.files.FilesService` over a
    :class:`~qgis_sdk.bridge.authority.HostAuthority` of its own. ``granted``
    lists the refs still live, oldest first, for assertions.
    """

    def __init__(self, scope: ResourceScope, *, owner: str = "plugin:test") -> None:
        super().__init__(HostAuthority(), scope, owner=owner)

    @property
    def granted(self) -> tuple:
        return self.authority.refs(self.binding)
