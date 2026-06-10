import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pf2e_map_tracker.io import load_graph_options, load_map_data
from pf2e_map_tracker.models import Character, CharacterGroup, MapData, NodeShape, Room

PRODUCTION_DATA = Path("data/room_data.json")
TEST_DATA = Path("tests/fixtures/test_data.json")


@pytest.mark.parametrize("path", [PRODUCTION_DATA, TEST_DATA])
def test_repository_map_data_is_valid(path: Path) -> None:
    assert load_map_data(path).rooms


def test_graph_options_are_valid() -> None:
    options = load_graph_options()
    assert options.physics.solver == "barnesHut"
    assert options.layout.random_seed == 41


def test_invalid_direction_fails_validation() -> None:
    data = _minimal_data()
    data["connections"][0]["direction"] = "sideways"

    with pytest.raises(ValidationError, match="direction"):
        MapData.model_validate(data)


def test_cross_reference_errors_are_aggregated() -> None:
    data = _minimal_data()
    data["characters"] = [{"name": "Lost", "ancestry": "Human", "group": "Missing Group"}]
    data["connections"][0].update({"from": "Missing Source", "status": "missing"})

    with pytest.raises(ValidationError) as error:
        MapData.model_validate(data)

    message = str(error.value)
    assert "unknown group 'Missing Group'" in message
    assert "unknown source room 'Missing Source'" in message
    assert "unknown status 'missing'" in message


def test_unknown_fields_are_rejected() -> None:
    data = _minimal_data()
    data["rooms"][0]["colour"] = "red"

    with pytest.raises(ValidationError, match="colour"):
        MapData.model_validate(data)


def test_character_requires_exactly_one_placement() -> None:
    data = _minimal_data()
    data["characters"] = [
        {
            "name": "Everywhere",
            "ancestry": "Human",
            "location": "A",
            "group": "Party",
        }
    ]

    with pytest.raises(ValidationError, match="exactly one"):
        MapData.model_validate(data)


def test_json_schema_uses_existing_wire_names() -> None:
    schema = json.dumps(MapData.model_json_schema(by_alias=True))
    assert "connectionStatus" in schema
    assert '"from"' in schema
    assert '"class"' in schema


def test_node_shapes_have_existing_defaults() -> None:
    assert Room(name="Room").shape == NodeShape.BOX
    assert CharacterGroup(name="Group", location="Room").shape == NodeShape.CIRCLE
    assert Character(name="Character", ancestry="Human", location="Room").shape == NodeShape.ELLIPSE


@pytest.mark.parametrize("shape", ["image", "circularImage", "icon", "pentagon"])
def test_unsupported_node_shape_fails_validation(shape: str) -> None:
    data = _minimal_data()
    data["rooms"][0]["shape"] = shape

    with pytest.raises(ValidationError, match="shape"):
        MapData.model_validate(data)


def _minimal_data() -> dict:
    return {
        "rooms": [{"name": "A"}, {"name": "B"}],
        "characters": [],
        "character_groups": [],
        "connections": [{"from": "A", "to": "B", "status": "open"}],
        "connectionStatus": [{"name": "open", "description": "Open"}],
    }
