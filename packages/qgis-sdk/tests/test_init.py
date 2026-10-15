from qgis_sdk import hello


def test_hello_returns_hello_world() -> None:
    assert hello() == "hello world"
