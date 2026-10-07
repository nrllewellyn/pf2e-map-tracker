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
PRODUCTION_DATA = REPOSITORY_ROOT / "data/map_data.json"
TEST_DATA = REPOSITORY_ROOT / "tests/fixtures/test_data.json"


@pytest.mark.parametrize("view", [None, {"position": {"x": -123.5, "y": 0}, "scale": 0.75}])
def test_optional_default_view_round_trips(view) -> None:
    data = MapData.model_validate({"defaultView": view})
    assert data.model_dump(by_alias=True)["defaultView"] == view
    assert MapData().default_view is None


@pytest.mark.parametrize("scale", [0, -1, float("inf"), float("nan"), True, "0.5", None])
def test_invalid_default_view_scale_is_rejected(scale) -> None:
    with pytest.raises(ValidationError, match="scale"):
        MapData.model_validate({"defaultView": {"position": {"x": 0, "y": 0}, "scale": scale}})


@pytest.mark.parametrize("position", [{"x": 0}, {"x": float("inf"), "y": 0}, None])
def test_invalid_default_view_position_is_rejected(position) -> None:
    with pytest.raises(ValidationError, match="position"):
        MapData.model_validate({"defaultView": {"position": position, "scale": 1}})


@pytest.mark.parametrize("path", [PRODUCTION_DATA, TEST_DATA])
def test_repository_map_data_is_valid(path: Path) -> None:
    assert load_map_data(path).rooms


def test_graph_options_are_valid() -> None:
    assert load_graph_options()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("interaction", "tooltipDelay"), -1),
        (("edges", "smooth"), {"type": "dynamic"}),
    ],
)
def test_invalid_graph_options_fail_validation(path: tuple[str, str], value: object) -> None:
    options = load_graph_options().model_dump(by_alias=True)
    options[path[0]][path[1]] = value

    with pytest.raises(ValidationError):
        GraphOptions.model_validate(options)


def test_missing_graph_options_fail_validation() -> None:
    options = load_graph_options().model_dump(by_alias=True)
    del options["interaction"]["tooltipDelay"]

    with pytest.raises(ValidationError, match="tooltipDelay"):
        GraphOptions.model_validate(options)


def test_unknown_graph_options_fail_validation() -> None:
    options = load_graph_options().model_dump(by_alias=True)
    options["interaction"]["unexpected"] = True

    with pytest.raises(ValidationError, match="unexpected"):
        GraphOptions.model_validate(options)


@pytest.mark.parametrize("field", ["layout", "physics"])
def test_removed_graph_options_are_rejected(field: str) -> None:
    options = load_graph_options().model_dump(by_alias=True)
    options[field] = {"enabled": True}
    with pytest.raises(ValidationError, match=field):
        GraphOptions.model_validate(options)


def test_room_position_is_required() -> None:
    data = _minimal_data()
    del data["rooms"][0]["position"]
    with pytest.raises(ValidationError, match="position"):
        MapData.model_validate(data)


@pytest.mark.parametrize("position", [{}, {"x": 0}, {"y": 0}, None])
def test_incomplete_room_positions_are_rejected(position: object) -> None:
    data = _minimal_data()
    data["rooms"][0]["position"] = position
    with pytest.raises(ValidationError, match="position"):
        MapData.model_validate(data)


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "12", True])
def test_invalid_room_coordinates_are_rejected(axis: str, value: object) -> None:
    data = _minimal_data()
    data["rooms"][0]["position"][axis] = value
    with pytest.raises(ValidationError, match=axis):
        MapData.model_validate(data)


@pytest.mark.parametrize("position", [{"x": 0, "y": 0}, {"x": -123.5, "y": -456}])
def test_zero_and_negative_room_positions_are_valid(position: dict) -> None:
    room = Room(id="room", name="Room", position=position)
    assert room.position.model_dump() == position


def test_removed_room_anchor_is_rejected() -> None:
    data = _minimal_data()
    data["rooms"][0]["anchor"] = True
    with pytest.raises(ValidationError, match="anchor"):
        MapData.model_validate(data)


@pytest.mark.parametrize(
    "collection,record",
    [
        ("character_groups", {"id": "party", "name": "Party", "location": "a"}),
        ("characters", {"name": "Hero", "ancestry": "Human", "location": "a"}),
    ],
)
def test_automatically_placed_nodes_do_not_accept_positions(collection: str, record: dict) -> None:
    data = _minimal_data()
    data[collection] = [{**record, "position": {"x": 0, "y": 0}}]
    with pytest.raises(ValidationError, match="position"):
        MapData.model_validate(data)


@pytest.mark.parametrize(
    "model,record",
    [
        (CharacterGroup, {"id": "party", "name": "Party", "location": "a"}),
        (Character, {"name": "Hero", "ancestry": "Human", "location": "a"}),
    ],
)
def test_optional_default_positions_round_trip_and_validate(model, record) -> None:
    assert model(**record).default_position is None
    assert "defaultPosition" not in model(**record).model_dump(by_alias=True, exclude_unset=True)
    for position in [None, {"x": 0, "y": 0}, {"x": -123.5, "y": 456.25}]:
        node = model.model_validate({**record, "defaultPosition": position})
        assert node.model_dump(by_alias=True)["defaultPosition"] == position
    for position in [
        {"x": 0},
        {"x": True, "y": 0},
        {"x": "12", "y": 0},
        {"x": float("inf"), "y": 0},
        {"x": 0, "y": float("nan")},
    ]:
        with pytest.raises(ValidationError, match="defaultPosition"):
            model.model_validate({**record, "defaultPosition": position})


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
    assert Room(id="room", name="Room", position={"x": 0, "y": 0}).shape == NodeShape.BOX
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
        "rooms": [
            {"id": "a", "name": "A", "position": {"x": 0, "y": 0}},
            {"id": "b", "name": "B", "position": {"x": 1200, "y": 0}},
        ],
        "characters": [],
        "character_groups": [],
        "connections": [{"from": "a", "to": "b", "status": "open"}],
        "connectionStatus": [{"id": "open", "description": "Open"}],
    }
