"""Shared compatibility policy for the optional Pydantic integration."""

SUPPORTED_PYDANTIC_VERSION = "2.14.1"
OPTIONAL_PYDANTIC_PROVISIONING_HINT = (
    f"Provision Pydantic {SUPPORTED_PYDANTIC_VERSION} or install the optional "
    "'qgis-sdk[controlled-deployment]' extra; the SDK will not install it "
    "automatically."
)
UNSUPPORTED_PYDANTIC_VERSION_HINT = (
    f"This prototype is verified only with Pydantic {SUPPORTED_PYDANTIC_VERSION}; "
    "provision that version or use a separately qualified adapter."
)
