import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pf2e_map_tracker.io import load_graph_options, load_map_data
from pf2e_map_tracker.models import (
    Character,
    CharacterGroup,
    GraphOptions,
    MapData,
    NodeShape,
    Room,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DATA = REPOSITORY_ROOT / "data/room_data.json"
TEST_DATA = REPOSITORY_ROOT / "tests/fixtures/test_data.json"


@pytest.mark.parametrize("path", [PRODUCTION_DATA, TEST_DATA])
def test_repository_map_data_is_valid(path: Path) -> None:
    assert load_map_data(path).rooms


def test_graph_options_are_valid() -> None:
    assert load_graph_options()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("layout", "randomSeed"), "not-an-integer"),
        (("physics", "solver"), "unsupported"),
    ],
)
def test_invalid_graph_options_fail_validation(path: tuple[str, str], value: str) -> None:
    options = load_graph_options().model_dump(by_alias=True)
    options[path[0]][path[1]] = value

    with pytest.raises(ValidationError):
        GraphOptions.model_validate(options)


def test_missing_graph_options_fail_validation() -> None:
    options = load_graph_options().model_dump(by_alias=True)
    del options["layout"]["randomSeed"]

    with pytest.raises(ValidationError, match="randomSeed"):
        GraphOptions.model_validate(options)


def test_unknown_graph_options_fail_validation() -> None:
    options = load_graph_options().model_dump(by_alias=True)
    options["layout"]["unexpected"] = True

    with pytest.raises(ValidationError, match="unexpected"):
        GraphOptions.model_validate(options)


def test_invalid_direction_fails_validation() -> None:
    data = _minimal_data()
    data["connections"][0]["direction"] = "sideways"

    with pytest.raises(ValidationError, match="direction"):
        MapData.model_validate(data)


def test_cross_reference_errors_are_aggregated() -> None:
    data = _minimal_data()
    data["characters"] = [{"name": "Lost", "ancestry": "Human", "group": "missing-group"}]
    data["connections"][0].update({"from": "missing-source", "status": "missing"})

    with pytest.raises(ValidationError) as error:
        MapData.model_validate(data)

    message = str(error.value)
    assert "unknown group 'missing-group'" in message
    assert "unknown source room 'missing-source'" in message
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
            "location": "a",
            "group": "party",
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
    assert Room(id="room", name="Room").shape == NodeShape.BOX
    assert CharacterGroup(id="group", name="Group", location="room").shape == NodeShape.CIRCLE
    assert Character(name="Character", ancestry="Human", location="room").shape == NodeShape.ELLIPSE


@pytest.mark.parametrize("shape", ["image", "circularImage", "icon", "pentagon"])
def test_unsupported_node_shape_fails_validation(shape: str) -> None:
    data = _minimal_data()
    data["rooms"][0]["shape"] = shape

    with pytest.raises(ValidationError, match="shape"):
        MapData.model_validate(data)


@pytest.mark.parametrize(
    "invalid_id",
    [
        "",
        "Uppercase",
        "two words",
        "two_words",
        "emoji-😀",
        "-leading",
        "trailing-",
        "two--hyphens",
    ],
)
def test_invalid_ids_fail_validation(invalid_id: str) -> None:
    data = _minimal_data()
    data["rooms"][0]["id"] = invalid_id

    with pytest.raises(ValidationError, match="id"):
        MapData.model_validate(data)


def test_ids_are_required() -> None:
    data = _minimal_data()
    del data["rooms"][0]["id"]

    with pytest.raises(ValidationError, match="id"):
        MapData.model_validate(data)


def test_unknown_is_reserved_for_connection_endpoints() -> None:
    data = _minimal_data()
    data["connections"][0]["to"] = "unknown"
    assert MapData.model_validate(data)

    data["rooms"][0]["id"] = "unknown"
    with pytest.raises(ValidationError, match="reserved for unknown connection endpoints"):
        MapData.model_validate(data)


def test_room_and_group_ids_are_globally_unique_but_names_may_repeat() -> None:
    data = _minimal_data()
    data["rooms"][1]["name"] = data["rooms"][0]["name"]
    data["character_groups"] = [{"id": "a", "name": "A", "location": "a"}]

    with pytest.raises(ValidationError, match="duplicate node id 'a'"):
        MapData.model_validate(data)

    data["character_groups"][0]["id"] = "group"
    assert MapData.model_validate(data)


def test_characters_do_not_accept_ids_and_names_must_be_unique() -> None:
    data = _minimal_data()
    data["characters"] = [
        {"name": "Same Name", "ancestry": "Human", "location": "a"},
        {"name": "Same Name", "ancestry": "Elf", "location": "b"},
    ]

    with pytest.raises(ValidationError, match="duplicate character name 'Same Name'"):
        MapData.model_validate(data)

    data["characters"][1]["name"] = "Different Name"
    data["characters"][0]["id"] = "character"
    with pytest.raises(ValidationError, match="id"):
        MapData.model_validate(data)


def test_status_ids_are_unique_in_separate_namespace() -> None:
    data = _minimal_data()
    data["connectionStatus"].append({"id": "open", "description": "Also open"})

    with pytest.raises(ValidationError, match="duplicate connection status id 'open'"):
        MapData.model_validate(data)

    data["connectionStatus"][1]["id"] = "a"
    assert MapData.model_validate(data)


def _minimal_data() -> dict:
    return {
        "rooms": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
        "characters": [],
        "character_groups": [],
        "connections": [{"from": "a", "to": "b", "status": "open"}],
        "connectionStatus": [{"id": "open", "description": "Open"}],
    }
