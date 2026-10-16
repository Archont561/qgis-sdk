"""The optional validator stays behind the default pure-Python import boundary."""

import builtins
import importlib

import pytest
from qgis_sdk.models import QgisSdkOptionalDependencyError


def test_adapter_module_import_does_not_import_pydantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_module = importlib.import_module("qgis_sdk.adapters.pydantic")
    original_import = builtins.__import__

    def reject_pydantic(name: str, *args: object, **kwargs: object) -> object:
        if name == "pydantic" or name.startswith("pydantic."):
            raise AssertionError(f"unexpected optional import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_pydantic)
    adapter_module = importlib.reload(adapter_module)

    assert adapter_module.PydanticContractAdapter.__name__ == "PydanticContractAdapter"


def test_pydantic_field_types_report_actionable_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    types_module = importlib.import_module("qgis_sdk.adapters.pydantic_types")
    original_import = builtins.__import__

    def reject_pydantic(name: str, *args: object, **kwargs: object) -> object:
        if name == "pydantic" or name.startswith("pydantic."):
            raise ModuleNotFoundError("blocked optional dependency")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", reject_pydantic)
        with pytest.raises(QgisSdkOptionalDependencyError) as caught:
            importlib.reload(types_module)

    assert caught.value.dependency == "pydantic"
    assert "controlled-deployment" in caught.value.installation_hint
    importlib.reload(types_module)
    assert (
        caught.value.installation_hint
        == types_module.OPTIONAL_PYDANTIC_PROVISIONING_HINT
    )


def test_adapter_rejects_an_unqualified_pydantic_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pydantic = importlib.import_module("pydantic")
    adapter_module = importlib.import_module("qgis_sdk.adapters.pydantic")
    monkeypatch.setattr(pydantic, "__version__", "2.14.2")

    with pytest.raises(QgisSdkOptionalDependencyError) as caught:
        adapter_module.PydanticContractAdapter(
            request_type=object,
            result_reader_type=object,
            result_writer_type=object,
            handler=lambda request: request,
        )

    assert caught.value.code == "optional_dependency_unavailable"
    assert (
        caught.value.installation_hint
        == adapter_module.UNSUPPORTED_PYDANTIC_VERSION_HINT
    )


def test_adapter_reports_actionable_error_when_pydantic_is_not_provisioned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_module = importlib.import_module("qgis_sdk.adapters.pydantic")
    original_import = builtins.__import__

    def reject_pydantic(name: str, *args: object, **kwargs: object) -> object:
        if name == "pydantic" or name.startswith("pydantic."):
            raise ModuleNotFoundError("blocked optional dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_pydantic)

    with pytest.raises(QgisSdkOptionalDependencyError) as caught:
        adapter_module.PydanticContractAdapter(
            request_type=object,
            result_reader_type=object,
            result_writer_type=object,
            handler=lambda request: request,
        )

    assert caught.value.code == "optional_dependency_unavailable"
    assert caught.value.dependency == "pydantic"
    assert "controlled-deployment" in caught.value.installation_hint
    assert (
        caught.value.installation_hint
        == adapter_module.OPTIONAL_PYDANTIC_PROVISIONING_HINT
    )
