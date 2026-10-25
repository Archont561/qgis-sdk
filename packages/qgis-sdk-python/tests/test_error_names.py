"""SDK-defined error names are unambiguous alongside host exceptions."""

import ast

import layers
from qgis_sdk import models


def test_public_sdk_exceptions_have_qgis_sdk_prefix() -> None:
    exception_names = {
        name
        for name, value in vars(models).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and issubclass(value, Exception)
    }

    assert {
        "QgisSdkError",
        "QgisSdkScopeClosedError",
        "QgisSdkUnsupportedCapabilityError",
        "QgisSdkOptionalDependencyError",
        "QgisSdkContractValidationError",
    } <= exception_names
    assert all(name.startswith("QgisSdk") for name in exception_names)


def test_sdk_defined_exception_classes_keep_the_prefix() -> None:
    source = layers.RUNTIME_SOURCE / "qgis_sdk"
    for path in source.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = (
                base.id if isinstance(base, ast.Name) else base.attr
                for base in node.bases
                if isinstance(base, (ast.Name, ast.Attribute))
            )
            is_exception = node.name.endswith(("Error", "Exception", "ExceptionGroup"))
            is_exception |= any(
                name.endswith(("Error", "Exception", "ExceptionGroup"))
                for name in bases
            )
            if is_exception:
                assert node.name.startswith("QgisSdk"), f"{path}: {node.name}"
