"""The package root keeps an explicit, reviewable public surface."""

import qgis_sdk


def test_public_surface_is_the_declarations_and_bindings_api() -> None:
    assert qgis_sdk.__all__ == [
        "ActionDescription",
        "PluginDescription",
        "QgisSdkDeclarationError",
        "StreamDescription",
        "action",
        "describe_bindings",
        "describe_plugin",
        "menu",
        "plugin",
        "shortcut",
        "stream",
        "toolbar",
    ]


def test_every_exported_name_resolves_on_the_package_root() -> None:
    missing = [name for name in qgis_sdk.__all__ if not hasattr(qgis_sdk, name)]
    assert missing == []
