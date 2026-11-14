"""The deprecation mark, the ``API001`` finding and the removal window.

decision-56 point 3 asks for three things at once: a mark that carries the
replacement and the removal version, a warning once per process when a caller
still uses the name, and ``check`` reporting the import as ``API001``. The fourth
is the promise itself - `release.py verify-api` refusing a removal before the
version the mark announced - which is tested here as data, without a release.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def warned_once_per_test():
    """Each test starts with nothing warned, so "once" means once."""
    from qgis_sdk import deprecation

    deprecation._WARNED.clear()
    yield
    deprecation._WARNED.clear()


def test_a_deprecated_function_warns_once_and_names_what_replaces_it():
    from qgis_sdk.deprecation import deprecated, deprecation_of

    @deprecated(since="0.12.0", removal="1.0.0", use="new_panel()")
    def old_panel() -> str:
        return "panel"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert old_panel() == "panel"
        old_panel()

    assert deprecation_of(old_panel).removal == "1.0.0"
    assert len(caught) == 1
    message = str(caught[0].message)
    assert "deprecated since 0.12.0" in message
    assert "removed in 1.0.0" in message
    assert "new_panel()" in message


def test_a_deprecated_class_warns_once_on_first_construction():
    from qgis_sdk.deprecation import deprecated

    @deprecated(since="0.12.0", removal="1.0.0", use="Panel")
    class OldPanel:
        """A retired panel."""

        def __init__(self, name: str) -> None:
            self.name = name

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first, second = OldPanel("a"), OldPanel("b")

    assert (first.name, second.name) == ("a", "b")
    assert len(caught) == 1


MARKS = {
    ("qgis_sdk.ui", "OldPanel"): None,
    ("qgis_sdk.models", "Legacy"): None,
}


def _marks():
    from qgis_sdk.deprecation import Deprecation

    return {
        "qgis_sdk.ui": Deprecation("0.12.0", "1.0.0", "Panel"),
        "qgis_sdk.models": Deprecation("0.12.0", "1.0.0", ""),
    }


def _table():
    marks = _marks()
    return {
        ("qgis_sdk.ui", "OldPanel"): marks["qgis_sdk.ui"],
        ("qgis_sdk.models", "Legacy"): marks["qgis_sdk.models"],
    }


def test_api001_reports_both_import_spellings_as_warnings():
    from qgis_sdk_tools.check.api import check_deprecated_usage

    source = """
from qgis_sdk.ui import Button, OldPanel
import qgis_sdk.models as models

panel = OldPanel()
legacy = models.Legacy()
"""

    found = check_deprecated_usage(
        source, path=Path("plugin.py"), deprecations=_table()
    )

    assert [(d.rule, d.line) for d in found] == [("API001", 2), ("API001", 6)]
    assert {d.severity for d in found} == {"warning"}
    assert "use Panel instead" in found[0].message
    assert "1.0.0" in found[0].remediation


def test_api001_says_nothing_about_a_name_that_is_not_marked():
    from qgis_sdk_tools.check.api import check_deprecated_usage

    source = "from qgis_sdk.ui import Button\n"
    found = check_deprecated_usage(
        source, path=Path("plugin.py"), deprecations=_table()
    )

    assert found == []


def _document(**sections) -> dict:
    """A minimal inventory document, with the deprecated name still present."""
    document = {
        "api_version": 1,
        "modules": {
            "qgis_sdk.ui": {"tier": "stable", "names": {"OldPanel": "()"}},
            "qgis_sdk.models": {"tier": "stable", "names": {"Legacy": "()"}},
        },
        "rules": [],
        "host_operations": [],
        "cli": [],
        "deprecations": [
            {
                "module": "qgis_sdk.ui",
                "name": "OldPanel",
                "since": "0.12.0",
                "removal": "1.0.0",
                "use": "Panel",
            }
        ],
    }
    document.update(sections)
    return document


def test_a_new_mark_is_deprecating_and_the_removal_is_breaking():
    from qgis_sdk_tools.api import diff, verdict

    marked = _document()
    unmarked = _document(deprecations=[])
    removed = _document(
        modules={
            "qgis_sdk.ui": {"tier": "stable", "names": {}},
            "qgis_sdk.models": _document()["modules"]["qgis_sdk.models"],
        }
    )

    assert verdict(diff(unmarked, marked)) == "deprecating"
    assert verdict(diff(marked, removed)) == "breaking"


@pytest.mark.parametrize(
    ("version", "reason"),
    [
        ("0.13.0", "announced for removal in 1.0.0"),
        # The SemVer rule fires first here: a removal after 1.0 is a major
        # whatever its window says, so the two refusals stay independent.
        ("1.1.0", "cannot ship as 1.1.0"),
        ("2.0.0", ""),
    ],
)
def test_verify_api_refuses_removing_a_name_before_its_window_closes(
    tmp_path: Path, version: str, reason: str
):
    from automation.release import _api
    from automation.release._history import QgisSdkReleaseError

    removed = _document(
        modules={
            "qgis_sdk.ui": {"tier": "stable", "names": {}},
            "qgis_sdk.models": {"tier": "stable", "names": {"Legacy": "()"}},
        }
    )
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    for path, document in ((old, _document()), (new, removed)):
        path.write_text(json.dumps(document), encoding="utf-8")
    arguments = _api.argparse.Namespace(
        baseline=str(old),
        current=str(new),
        tag="",
        version=version,
        check=False,
        json=False,
    )

    if not reason:
        assert _api.cmd_verify_api(arguments) == 0
        return
    with pytest.raises(QgisSdkReleaseError, match=reason):
        _api.cmd_verify_api(arguments)


def test_the_inventory_records_a_mark_where_a_symbol_carries_one():
    """The dump reads the marks off the installed package, not off a list."""
    from qgis_sdk_tools.api import inventory

    document = inventory().document()

    assert isinstance(document["deprecations"], list)
    for entry in document["deprecations"]:
        assert {"module", "name", "since", "removal", "use"} == set(entry)
