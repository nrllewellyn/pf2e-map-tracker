import json
import math
import re
import tomllib
from pathlib import Path

import pytest

from pf2e_map_tracker.graph import (
    UNKNOWN_ROOM_COLOR,
    UNKNOWN_ROOM_NAME,
    build_network,
    generate_graph,
)
from pf2e_map_tracker.html_enhancements import INJECTION_MARKER, inject_enhancements
from pf2e_map_tracker.io import load_map_data
from pf2e_map_tracker.models import Character, MapData, Position, Room
from pf2e_map_tracker.tooltips import character_tooltip, room_tooltips

TEST_DATA = Path(__file__).resolve().parent / "fixtures/test_data.json"


def test_build_network_contains_all_nodes_and_edges() -> None:
    data = load_map_data(TEST_DATA)
    network = build_network(data)

    assert len(network.nodes) == len(data.rooms) + len(data.characters) + len(data.character_groups)
    expected_placement_edges = len(data.characters) + len(data.character_groups)
    assert len(network.edges) == len(data.connections) + expected_placement_edges


def test_network_uses_ids_for_links_and_names_for_display() -> None:
    data = MapData.model_validate(
        {
            "rooms": [
                {"id": "source-room", "name": "Shared Name", "position": {"x": 0, "y": 0}},
                {"id": "target-room", "name": "Shared Name", "position": {"x": 1200, "y": 0}},
            ],
            "character_groups": [
                {"id": "group", "name": "Display Group", "location": "source-room"}
            ],
            "characters": [
                {
                    "name": "Display Character",
                    "ancestry": "Human",
                    "group": "group",
                }
            ],
            "connections": [{"from": "source-room", "to": "target-room", "status": "open"}],
            "connectionStatus": [{"id": "open", "description": "Open"}],
        }
    )

    network = build_network(data)
    nodes = {node["id"]: node for node in network.nodes}
    connection = network.edges[0]

    assert nodes["source-room"]["label"] == "Shared Name"
    assert nodes["__character-0"]["label"] == "Display Character"
    assert "Display Group" in nodes["__character-0"]["title"]
    assert connection["from"] == "source-room"
    assert connection["to"] == "target-room"
    assert "Shared Name" in connection["title"]


def test_unknown_connection_endpoints_create_separate_virtual_rooms() -> None:
    data = MapData.model_validate(
        {
            "rooms": [{"id": "room", "name": "Known Room", "position": {"x": 0, "y": 0}}],
            "connections": [
                {"from": "room", "to": "unknown", "status": "open"},
                {"from": "unknown", "to": "room", "status": "open"},
                {"from": "unknown", "to": "unknown", "status": "open"},
            ],
            "connectionStatus": [{"id": "open", "description": "Open"}],
        }
    )

    network = build_network(data)
    unknown_nodes = [node for node in network.nodes if node["id"].startswith("__unknown-")]
    unknown_edges = network.edges

    assert len(unknown_nodes) == 4
    assert all(node["label"] == UNKNOWN_ROOM_NAME for node in unknown_nodes)
    assert all(node["color"] == UNKNOWN_ROOM_COLOR for node in unknown_nodes)
    assert unknown_edges[0]["to"] == "__unknown-0-target"
    assert unknown_edges[1]["from"] == "__unknown-1-source"
    assert unknown_edges[2]["from"] == "__unknown-2-source"
    assert unknown_edges[2]["to"] == "__unknown-2-target"
    assert all(UNKNOWN_ROOM_NAME in edge["title"] for edge in unknown_edges)
    assert all(node["fixed"] is False and node["physics"] is True for node in unknown_nodes)
    assert all(edge["physics"] is True for edge in unknown_edges)
    near_room = unknown_nodes[:2]
    assert len({(node["x"], node["y"]) for node in near_room}) == 2
    assert all(0 < math.hypot(node["x"], node["y"]) < 500 for node in near_room)


def test_rooms_use_saved_positions_and_are_fixed_spring_endpoints() -> None:
    data = load_map_data(TEST_DATA)
    network = build_network(data)
    nodes = {node["id"]: node for node in network.nodes}
    for room in data.rooms:
        assert nodes[room.id]["x"] == room.position.x
        assert nodes[room.id]["y"] == room.position.y
        assert nodes[room.id]["fixed"] == {"x": True, "y": True}
        assert nodes[room.id]["physics"] is True
    assert all("mass" not in node for node in network.nodes)
    assert all(not edge.get("hidden") for edge in network.edges)


def test_physics_only_uses_attachment_edges() -> None:
    data = load_map_data(TEST_DATA)
    network = build_network(data)
    assert all(edge["physics"] is False for edge in network.edges[: len(data.connections)])
    assert all(edge["physics"] is True for edge in network.edges[len(data.connections) :])
    assert all(
        node["physics"] is True and node["fixed"] is False
        for node in network.nodes
        if node["node_type"] != "room"
    )
    options = network.options
    assert options["layout"]["improvedLayout"] is False
    assert options["layout"]["hierarchical"]["enabled"] is False
    assert options["interaction"]["dragNodes"] is False
    assert options["physics"]["barnesHut"]["centralGravity"] == 0
    assert options["physics"]["barnesHut"]["avoidOverlap"] > 0
    assert options["physics"]["stabilization"]["enabled"] is True
    assert options["edges"]["smooth"]["type"] != "dynamic"


def test_crowded_room_seeds_are_distinct_nearby_and_deterministic() -> None:
    data = MapData.model_validate(
        {
            "rooms": [{"id": "room", "name": "Room", "position": {"x": -1000, "y": 500}}],
            "character_groups": [
                {"id": "first", "name": "First", "location": "room"},
                {"id": "second", "name": "Second", "location": "room"},
            ],
            "characters": [
                *[
                    {"name": f"Direct {index}", "ancestry": "Human", "location": "room"}
                    for index in range(19)
                ],
                {"name": "First member", "ancestry": "Elf", "group": "first"},
                {"name": "Second member", "ancestry": "Elf", "group": "second"},
            ],
            "connections": [{"from": "room", "to": "unknown", "status": "open"} for _ in range(3)],
            "connectionStatus": [{"id": "open", "description": "Open"}],
        }
    )
    network = build_network(data)
    assert network.nodes == build_network(data).nodes
    nodes = {node["id"]: node for node in network.nodes}
    siblings = [
        node
        for node in network.nodes
        if node["id"] not in ("room", "__character-19", "__character-20")
    ]
    assert len({(node["x"], node["y"]) for node in siblings}) == len(siblings)
    assert all(0 < math.hypot(node["x"] + 1000, node["y"] - 500) < 1000 for node in siblings)
    for node_id, parent_id in [("__character-19", "first"), ("__character-20", "second")]:
        node, parent = nodes[node_id], nodes[parent_id]
        assert 0 < math.hypot(node["x"] - parent["x"], node["y"] - parent["y"]) < 500
    assert all(edge["physics"] is True for edge in network.edges)


def test_seeds_follow_changed_room_coordinates_and_placement_references() -> None:
    data = load_map_data(TEST_DATA)
    before = {node["id"]: node for node in build_network(data).nodes}
    data.rooms[0].position.x += 700
    data.rooms[0].position.y -= 300
    after = {node["id"]: node for node in build_network(data).nodes}
    for node_id in ["entrance", "pathfinders", "__character-0"]:
        assert after[node_id]["x"] == pytest.approx(before[node_id]["x"] + 700)
        assert after[node_id]["y"] == pytest.approx(before[node_id]["y"] - 300)
    assert after["kitchen"] == before["kitchen"]

    data.character_groups[0].location = "basement-hall"
    data.characters[1].location = "garage"
    relocated = {node["id"]: node for node in build_network(data).nodes}
    for node_id, parent_id in [
        ("pathfinders", "basement-hall"),
        ("__character-0", "pathfinders"),
        ("__character-1", "garage"),
    ]:
        node, parent = relocated[node_id], relocated[parent_id]
        assert 0 < math.hypot(node["x"] - parent["x"], node["y"] - parent["y"]) < 500


def test_default_positions_override_seeds_and_group_members_follow_default_group() -> None:
    data = MapData.model_validate(
        {
            "rooms": [{"id": "room", "name": "Room", "position": {"x": 0, "y": 0}}],
            "character_groups": [{"id": "party", "name": "Party", "location": "room"}],
            "characters": [
                {"name": "Member", "ancestry": "Human", "group": "party"},
                {"name": "Direct", "ancestry": "Human", "location": "room"},
                {"name": "Automatic", "ancestry": "Human", "location": "room"},
            ],
            "connections": [{"from": "room", "to": "unknown", "status": "open"}],
            "connectionStatus": [{"id": "open", "description": "Open"}],
        }
    )
    original = {node["id"]: node for node in build_network(data).nodes}
    group_position = Position(x=-123.5, y=456.25)
    direct_position = Position(x=0, y=0)
    data.character_groups[0].default_position = group_position
    data.characters[1].default_position = direct_position
    nodes = {node["id"]: node for node in build_network(data).nodes}
    assert (nodes["party"]["x"], nodes["party"]["y"]) == (-123.5, 456.25)
    assert (nodes["__character-1"]["x"], nodes["__character-1"]["y"]) == (0, 0)
    member, group = nodes["__character-0"], nodes["party"]
    assert member["x"] - group["x"] == pytest.approx(
        original["__character-0"]["x"] - original["party"]["x"]
    )
    assert member["y"] - group["y"] == pytest.approx(
        original["__character-0"]["y"] - original["party"]["y"]
    )
    for node_id in ["room", "__character-2", "__unknown-0-target"]:
        assert nodes[node_id] == original[node_id]
    assert all(
        node["fixed"] is False and node["physics"] is True
        for node in nodes.values()
        if node["node_type"] != "room"
    )
    data.characters[0].default_position = Position(x=800.5, y=-700.25)
    member = next(node for node in build_network(data).nodes if node["id"] == "__character-0")
    assert (member["x"], member["y"]) == (800.5, -700.25)
    data.character_groups[0].default_position = None
    for character in data.characters:
        character.default_position = None
    assert build_network(data).nodes == list(original.values())


@pytest.mark.parametrize("with_room", [True, False])
def test_unknown_only_pairs_seed_outside_the_room_grid(with_room: bool) -> None:
    data = MapData.model_validate(
        {
            "rooms": (
                [{"id": "room", "name": "Room", "position": {"x": 5000, "y": -600}}]
                if with_room
                else []
            ),
            "connections": [
                {"from": "unknown", "to": "unknown", "status": "open"} for _ in range(2)
            ],
            "connectionStatus": [{"id": "open", "description": "Open"}],
        }
    )
    network = build_network(data)
    unknown_nodes = [node for node in network.nodes if node["id"].startswith("__unknown-")]
    assert len({(node["x"], node["y"]) for node in unknown_nodes}) == 4
    assert all(node["x"] > (5000 if with_room else 0) for node in unknown_nodes)
    assert all(node["fixed"] is False and node["physics"] is True for node in unknown_nodes)
    assert all(edge["physics"] is True for edge in network.edges)


def test_empty_map_builds_without_inferred_positions() -> None:
    network = build_network(MapData())
    assert network.nodes == []
    assert network.edges == []


def test_cycles_parallel_connections_and_arrow_directions_are_preserved() -> None:
    directions = ["forward_only", "backward_only", "bidirectional", "bidirectional"]
    endpoints = [("a", "b"), ("b", "c"), ("c", "a"), ("a", "b")]
    data = MapData.model_validate(
        {
            "rooms": [
                {"id": room, "name": room, "position": {"x": index * 1200, "y": 0}}
                for index, room in enumerate(["a", "b", "c", "disconnected"])
            ],
            "connections": [
                {"from": source, "to": target, "status": "open", "direction": direction}
                for (source, target), direction in zip(endpoints, directions, strict=True)
            ],
            "connectionStatus": [{"id": "open", "description": "Open"}],
        }
    )
    network = build_network(data)
    assert len(network.nodes) == 4
    assert [(edge["from"], edge["to"]) for edge in network.edges] == endpoints
    assert [
        (edge["arrows"]["from"]["enabled"], edge["arrows"]["to"]["enabled"])
        for edge in network.edges
    ] == [(False, True), (True, False), (True, True), (True, True)]
    assert all(edge["physics"] is False for edge in network.edges)


def test_generate_graph_serializes_saved_coordinates_and_runtime_options(tmp_path: Path) -> None:
    content = generate_graph(TEST_DATA, tmp_path / "map.html").read_text(encoding="utf-8")
    serialized_nodes = json.loads(re.search(r"nodes = new vis.DataSet\((\[.*?\])\);", content)[1])
    options = json.loads(re.search(r"var options = (\{.*?\});", content)[1])
    nodes = {node["id"]: node for node in serialized_nodes}
    for room in load_map_data(TEST_DATA).rooms:
        assert nodes[room.id]["x"] == room.position.x
        assert nodes[room.id]["y"] == room.position.y
        assert nodes[room.id]["fixed"] == {"x": True, "y": True}
    assert options["interaction"]["dragNodes"] is False
    assert options["physics"]["enabled"] is True
    assert options["layout"]["improvedLayout"] is False


def test_generate_graph_injects_enhancements_once(tmp_path: Path) -> None:
    output = generate_graph(TEST_DATA, tmp_path / "nested" / "map.html")
    inject_enhancements(output)

    content = output.read_text(encoding="utf-8")
    assert content.count(INJECTION_MARKER) == 1
    assert "setupCharacterVisibility" in content
    assert "setupNodeSelectorLabels" in content
    assert "Valeros" in content


def test_generate_graph_includes_version_and_build_time(tmp_path: Path) -> None:
    output = generate_graph(TEST_DATA, tmp_path / "map.html")

    content = output.read_text(encoding="utf-8")
    with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as pyproject:
        expected_version = tomllib.load(pyproject)["project"]["version"]

    assert f'"version": "{expected_version}"' in content
    assert re.search(
        r'"builtAt": "\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} GMT[+-]\d{2}:\d{2}"',
        content,
    )
    assert "program-version" in content
    assert "build-date" in content


def test_trusted_html_is_preserved_in_tooltips() -> None:
    character = Character(
        name="Merisiel",
        ancestry="Elf",
        location="kitchen",
        other_details="<b>trusted</b>",
    )
    room = Room(id="kitchen", name="Kitchen", position={"x": 0, "y": 0}, notes="<p>trusted</p>")

    assert "<b>trusted</b>" in character_tooltip(character, "Kitchen")
    assert "<p>trusted</p>" in room_tooltips(room, [], [])[0]


def test_node_shape_overrides_are_added_to_network() -> None:
    data = MapData.model_validate(
        {
            "rooms": [
                {"id": "room", "name": "Room", "position": {"x": 0, "y": 0}, "shape": "star"}
            ],
            "character_groups": [
                {"id": "group", "name": "Group", "location": "room", "shape": "triangle"}
            ],
            "characters": [
                {
                    "name": "Character",
                    "ancestry": "Human",
                    "group": "group",
                    "shape": "diamond",
                }
            ],
        }
    )

    nodes = {node["id"]: node for node in build_network(data).nodes}

    assert nodes["room"]["shape"] == "star"
    assert nodes["group"]["shape"] == "triangle"
    assert nodes["__character-0"]["shape"] == "diamond"


def test_generate_graph_preserves_emojis_in_displayed_text_and_references(tmp_path: Path) -> None:
    emoji_values = [
        "Room 🏰",
        "Notes 📝",
        "Other Room 🚪",
        "Party 🛡️",
        "Hero 🧙",
        "Elf 🧝",
        "Wizard ✨",
        "Description 👀",
        "Personality 😀",
        "Details 🔮",
        "Open door 🚶",
        "Passage ↗️",
        "Connection notes 🧭",
    ]
    data = {
        "rooms": [
            {
                "id": "room-castle",
                "name": "Room 🏰",
                "position": {"x": 0, "y": 0},
                "notes": "Notes 📝",
            },
            {"id": "other-room", "name": "Other Room 🚪", "position": {"x": 1200, "y": 0}},
        ],
        "character_groups": [{"id": "party", "name": "Party 🛡️", "location": "room-castle"}],
        "characters": [
            {
                "name": "Hero 🧙",
                "ancestry": "Elf 🧝",
                "class": "Wizard ✨",
                "physical_description": "Description 👀",
                "personality": "Personality 😀",
                "other_details": "Details 🔮",
                "group": "party",
            }
        ],
        "connections": [
            {
                "from": "room-castle",
                "to": "other-room",
                "status": "open",
                "name": "Passage ↗️",
                "notes": "Connection notes 🧭",
            }
        ],
        "connectionStatus": [{"id": "open", "description": "Open door 🚶"}],
    }
    input_path = tmp_path / "emoji.json"
    output_path = tmp_path / "emoji.html"
    input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    loaded = load_map_data(input_path)
    generate_graph(input_path, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert loaded.connections[0].status == "open"
    assert all(value in content for value in emoji_values)


def test_generate_graph_preserves_emoji_presentation_selector(tmp_path: Path) -> None:
    emoji_label = "Room \U0001f6e1\ufe0f"
    data = {"rooms": [{"id": "room", "name": emoji_label, "position": {"x": 0, "y": 0}}]}
    input_path = tmp_path / "emoji-presentation.json"
    output_path = tmp_path / "emoji-presentation.html"
    input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    network = build_network(load_map_data(input_path))
    generate_graph(input_path, output_path)

    assert network.nodes[0]["label"] == emoji_label
    assert emoji_label in output_path.read_text(encoding="utf-8")
