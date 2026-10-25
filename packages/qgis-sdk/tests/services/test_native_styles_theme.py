"""Native-only: applying a layer style must not touch the application theme.

decision-16 separates layer styling from UI theming. Review alone cannot show
that, so this module reads the application's own stylesheet and palette before
and after a style application and asserts they are identical, and reads the
layer's renderer before and after a refused application to prove nothing partial
was left behind.

It needs a real QGIS host, so it is skipped unless ``QGIS_SDK_NATIVE_SERVICES=1``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.models import QgisSdkStyleIncompatibleError

pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    from .conftest import Services

# The roles a QGIS theme actually paints with: window and page backgrounds, text,
# buttons and selection. Comparing a fixed set keeps a failure readable.
THEME_ROLES = (
    "Window",
    "WindowText",
    "Base",
    "Text",
    "Button",
    "Highlight",
)


def _theme_snapshot() -> tuple[object, ...]:
    from PyQt6.QtWidgets import QApplication

    application = QApplication.instance()
    palette = application.palette()
    colours = tuple(
        palette.color(getattr(palette.ColorRole, role)).name() for role in THEME_ROLES
    )
    return (application.styleSheet(), colours)


def _renderer_signature(services: Services, layer_id: str) -> tuple[object, ...]:
    # White-box, deliberately: this reads the adapter's own native layer, because
    # no contract method exposes a renderer and one should not exist for a test.
    layer = services.layers._qgs_layer(layer_id)  # type: ignore[attr-defined]
    symbol = layer.renderer().symbol()
    return (layer.renderer().type(), symbol.type(), symbol.color().name())


def test_applying_a_packaged_style_leaves_the_application_theme_unchanged(
    native_services: Services,
) -> None:
    before = _theme_snapshot()
    info = native_services.layers.open_vector(native_services.dataset)

    native_services.styles.apply_style(info.id, native_services.compatible_style)

    assert _theme_snapshot() == before


def test_a_refused_style_leaves_the_renderer_untouched(
    native_services: Services,
) -> None:
    lines = native_services.layers.open_vector(native_services.line_dataset)
    before = _renderer_signature(native_services, lines.id)

    with pytest.raises(QgisSdkStyleIncompatibleError):
        native_services.styles.apply_style(lines.id, native_services.compatible_style)

    assert _renderer_signature(native_services, lines.id) == before


def test_an_applied_style_changes_the_layer_renderer(
    native_services: Services,
) -> None:
    info = native_services.layers.open_vector(native_services.dataset)
    before = _renderer_signature(native_services, info.id)

    native_services.styles.apply_style(info.id, native_services.compatible_style)

    assert _renderer_signature(native_services, info.id) != before
