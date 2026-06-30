import pytest

from app.connectors.common.types import ConnectorCapabilities, ConnectorType


def test_connector_type_values():
    assert ConnectorType.SOURCE.value == "source"
    assert ConnectorType.DESTINATION.value == "destination"


def test_capabilities_defaults_all_false():
    caps = ConnectorCapabilities()
    assert caps.can_list_folders is False
    assert caps.can_list_files is False
    assert caps.can_list_worksheets is False
    assert caps.can_read_worksheet is False
    assert caps.can_get_metadata is False
    assert caps.can_watch_changes is False
    assert caps.can_list_products is False
    assert caps.can_read_inventory is False
    assert caps.extra == {}


def test_capabilities_frozen():
    caps = ConnectorCapabilities(can_list_folders=True)
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        caps.can_list_folders = False  # type: ignore[misc]


def test_capabilities_partial():
    caps = ConnectorCapabilities(can_list_folders=True, can_list_files=True)
    assert caps.can_list_folders is True
    assert caps.can_list_files is True
    assert caps.can_list_worksheets is False


def test_capabilities_extra():
    caps = ConnectorCapabilities(extra={"can_stream": True})
    assert caps.extra["can_stream"] is True
