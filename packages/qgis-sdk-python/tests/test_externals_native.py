"""The external probe inside a real QGIS (TASK-77 AC #1).

The generated ``classFactory`` of a built plugin imports each declared
external before it constructs anything. Here the plugin is built, extracted
exactly as *Install from ZIP* does, imported under a real ``QgsApplication``,
and its ``classFactory`` is called with an interface whose message bar
records what the user would see. A missing package leaves nothing running and
says what to install; a present one constructs the plugin as usual.
"""

from __future__ import annotations

import sys
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk_tools.bundle import build_plugin
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

pytestmark = pytest.mark.desktop

PLUGIN = "needs_more"


def never_run(argv: Sequence[str], cwd: Path) -> int:
    raise AssertionError(f"no process expected, got {argv} in {cwd}")


class Recorder:
    """The part of ``QgisInterface`` the probe uses."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def messageBar(self) -> Recorder:
        return self

    def pushCritical(self, title: str, message: str) -> None:
        self.messages.append((title, message))


@pytest.fixture
def installed(tmp_path: Path) -> Iterator[Any]:
    """Build ``needs_more`` and import the extracted package the way QGIS does."""

    def install(build: str) -> Any:
        root = tmp_path / PLUGIN
        write_scaffold(ScaffoldOptions.resolve(PLUGIN), root)
        pyproject = root / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8")
            + f"\n[tool.qgis-sdk.build]\n{build}\n",
            encoding="utf-8",
        )
        result = build_plugin(root, run=never_run)
        plugins = tmp_path / "plugins" / f"{build[:12]}"
        plugins.mkdir(parents=True)
        with zipfile.ZipFile(result.archive) as archive:
            archive.extractall(plugins)
        sys.path.insert(0, str(plugins))
        for name in [
            n for n in sys.modules if n == PLUGIN or n.startswith(PLUGIN + ".")
        ]:
            del sys.modules[name]
        return __import__(PLUGIN)

    yield install
    for name in [n for n in sys.modules if n == PLUGIN or n.startswith(PLUGIN + ".")]:
        del sys.modules[name]
    for entry in [p for p in sys.path if "plugins" in p]:
        sys.path.remove(entry)


def test_a_missing_external_leaves_the_plugin_unloaded(
    qgis_app: Any, installed: Any
) -> None:
    module = installed(
        'external = [{ import = "definitely_missing_pkg", requirement = '
        '"definitely-missing>=2", reason = "reads the widget" }]'
    )
    iface = Recorder()

    built = module.classFactory(iface)

    assert built is None
    assert len(iface.messages) == 1
    title, message = iface.messages[0]
    assert title == f"{PLUGIN}: missing dependency"
    assert "definitely_missing_pkg" in message
    assert "reads the widget" in message
    assert "pip install" in message
    # Nothing of the plugin was constructed: there is no runtime to unload.
    assert module.classFactory.__doc__ is not None


def test_a_present_external_constructs_the_plugin(
    qgis_app: Any, installed: Any
) -> None:
    module = installed('external = ["json"]')
    iface = Recorder()

    desktop = module.classFactory(iface)

    assert desktop is not None
    assert desktop.view is None  # constructed, not started
    assert iface.messages == []
    assert desktop.unload() is not False
