"""Print layouts on the wire: descriptions in, refs out, never a path.

TASK-89 wants the same three properties on the host surface that the plugin API
gives: a layout the project holds is *described*, a render *writes a file*, and
what the page receives for it is a ref the host minted for that page - the
exporter's path never crosses (decision-20). The export also replaces a file the
page's own write ref names, which is why both render operations carry the
destructive annotation; the annotation set is pinned in
``test_bridge_host_project.py`` beside the other operations that discard state.

The double is the runtime's own ``FakeLayouts``, so these tests say something
about the handler, the schemas and the ref minting rather than about rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk.bridge import BridgeErrorCode, Dispatcher
from qgis_sdk.bridge.authority import FileOperation, HostAuthority
from qgis_sdk.bridge.host import HostServices, register_host_operations
from qgis_sdk.bridge.protocol import BRIDGE_PROTOCOL_VERSION
from qgis_sdk.core import ResourceScope
from qgis_sdk.files import FilesService
from qgis_sdk.testing import (
    FakeLayers,
    FakeLayouts,
    FakeProject,
    FakeWorkers,
    RecordingNotifications,
)

ORIGIN = "qgis://desktop"

#: The layout the double declares: two pages, no atlas.
LAYOUT = "report"
SINGLE_PAGE = "cover"
ATLAS = "atlas"
COVERAGE = "points"
FEATURE_IDS = (1, 3, 7)


@dataclass
class _Doubles:
    """The fakes the bridge is handed, plus the refs the page holds."""

    scope: ResourceScope
    layouts: FakeLayouts
    files: FilesService
    services: HostServices

    @property
    def authority(self) -> HostAuthority:
        return self.services.authority


@dataclass
class _Styles:
    def apply_style(self, layer_id: str, style: str) -> None:  # pragma: no cover
        raise AssertionError("styles are not part of this slice")


@dataclass
class _Settings:
    def get(
        self, key: str, default: str | None = None
    ) -> str | None:  # pragma: no cover
        return default


@pytest.fixture
def doubles(tmp_path: Path) -> _Doubles:
    scope = ResourceScope()
    authority = HostAuthority()
    # One authority on both sides: the view's refs and the plugin's are the same
    # refs, which is how this host is wired in production too.
    files = FilesService(authority, scope, owner="plugin:demo")
    layouts = FakeLayouts(
        scope,
        workers=FakeWorkers(),
        files=files,
        working_directory=tmp_path / "exports",
    )
    (tmp_path / "exports").mkdir(parents=True, exist_ok=True)
    layouts.declare_layout(LAYOUT, pages=2)
    layouts.declare_layout(SINGLE_PAGE)
    layouts.declare_atlas(
        ATLAS, coverage_layer=COVERAGE, feature_ids=FEATURE_IDS, pages=1
    )
    layers = FakeLayers(scope)
    services = HostServices(
        layers=layers,
        project=FakeProject(layers, scope),
        settings=_Settings(),  # type: ignore[arg-type]
        styles=_Styles(),  # type: ignore[arg-type]
        notifications=RecordingNotifications(scope),
        authority=authority,
        files=files,
        layouts=layouts,
    )
    return _Doubles(scope=scope, layouts=layouts, files=files, services=services)


def _dispatcher(doubles: _Doubles) -> Dispatcher:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    register_host_operations(dispatcher, doubles.services)
    return dispatcher


def _call(
    dispatcher: Dispatcher, operation: str, payload: Any = None, *, binding: Any = None
) -> dict:
    if binding is None:
        binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": operation,
            "payload": {} if payload is None else payload,
        },
    )


# -- listing and templates ---------------------------------------------------


def test_the_layouts_cross_as_described_models(doubles: _Doubles) -> None:
    dispatcher = _dispatcher(doubles)

    answered = _call(dispatcher, "layouts.list")

    assert answered["ok"] is True
    described = {entry["name"]: entry for entry in answered["value"]["items"]}
    assert set(described) == {LAYOUT, SINGLE_PAGE, ATLAS}
    assert described[LAYOUT]["id"] == LAYOUT
    assert described[LAYOUT]["page_count"] == 2
    assert described[LAYOUT]["atlas"] is None
    assert described[ATLAS]["atlas"]["coverage_layer"] == COVERAGE
    assert "path" not in described[LAYOUT]


def test_a_template_crosses_as_a_ref_and_answers_the_new_layout(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    template = tmp_path / "sheet.qpt"
    template.write_text("<Layout/>", encoding="utf-8")
    ref = doubles.authority.grant_file(binding, template)

    answered = _call(dispatcher, "layouts.load_template", {"file": ref.to_wire()})

    assert answered["ok"] is True
    assert answered["value"]["name"] == "sheet"
    assert answered["value"]["page_count"] == 1


def test_a_path_is_not_a_ref_on_this_side_either(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)

    answered = _call(
        dispatcher, "layouts.load_template", {"file": str(tmp_path / "sheet.qpt")}
    )

    assert answered["ok"] is False
    assert answered["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value


# -- one export --------------------------------------------------------------


def test_an_export_answers_a_ref_never_the_path_it_wrote(
    doubles: _Doubles,
) -> None:
    dispatcher = _dispatcher(doubles)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    answered = _call(dispatcher, "layouts.export", {"layout": LAYOUT, "format": "pdf"})

    assert answered["ok"] is True
    value = answered["value"]
    assert "path" not in value
    assert value["file"]["kind"] == "file"
    assert value["format"] == "pdf"
    assert value["pages"] == 2
    assert value["bytes"] > 0
    written = doubles.authority.resolve_file(binding, value["file"], FileOperation.READ)
    assert written.suffix == ".pdf"
    assert written.is_file()


def test_an_export_writes_where_the_pages_write_ref_names(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    destination = tmp_path / "chosen.pdf"
    ref = doubles.authority.grant_file(
        binding, destination, operations=(FileOperation.WRITE,), overwrite=True
    )

    answered = _call(
        dispatcher,
        "layouts.export",
        {"layout": LAYOUT, "format": "pdf", "destination": ref.to_wire()},
    )

    assert answered["ok"] is True
    assert destination.is_file()


def test_replacing_a_file_the_page_named_needs_the_flag(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    destination = tmp_path / "chosen.pdf"
    destination.write_text("an earlier export", encoding="utf-8")
    ref = doubles.authority.grant_file(
        binding, destination, operations=(FileOperation.WRITE,), overwrite=True
    )
    payload = {"layout": LAYOUT, "format": "pdf", "destination": ref.to_wire()}

    refused = _call(dispatcher, "layouts.export", payload)

    assert refused["ok"] is False
    assert "overwrit" in refused["error"]["message"]

    allowed = _call(dispatcher, "layouts.export", {**payload, "overwrite": True})

    assert allowed["ok"] is True
    assert destination.is_file()


def test_an_unknown_layout_is_refused_by_name(doubles: _Doubles) -> None:
    dispatcher = _dispatcher(doubles)

    answered = _call(dispatcher, "layouts.export", {"layout": "no-such-layout"})

    assert answered["ok"] is False
    assert "no-such-layout" in answered["error"]["message"]


def test_an_unknown_format_is_refused_before_the_exporter_runs(
    doubles: _Doubles,
) -> None:
    dispatcher = _dispatcher(doubles)

    answered = _call(dispatcher, "layouts.export", {"layout": LAYOUT, "format": "tiff"})

    assert answered["ok"] is False
    assert answered["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value


# -- the atlas ---------------------------------------------------------------


def test_the_atlas_answers_one_ref_per_page(doubles: _Doubles) -> None:
    dispatcher = _dispatcher(doubles)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    answered = _call(
        dispatcher,
        "layouts.atlas",
        {"layout": ATLAS, "format": "pdf", "pattern": "sheet-{index:02d}"},
    )

    assert answered["ok"] is True
    value = answered["value"]
    assert value["format"] == "pdf"
    assert [page["index"] for page in value["pages"]] == [1, 2, 3]
    assert [page["feature_id"] for page in value["pages"]] == list(FEATURE_IDS)
    directory = doubles.authority.resolve_file(
        binding, value["directory"], FileOperation.READ
    )
    for page in value["pages"]:
        written = doubles.authority.resolve_file(
            binding, page["file"], FileOperation.READ
        )
        assert written.parent == directory
        assert written.is_file()
        assert "path" not in page


def test_an_atlas_pattern_may_not_name_an_unknown_field(doubles: _Doubles) -> None:
    dispatcher = _dispatcher(doubles)

    answered = _call(
        dispatcher, "layouts.atlas", {"layout": ATLAS, "pattern": "{page}.{index}"}
    )

    assert answered["ok"] is False
    assert "page" in answered["error"]["message"]
