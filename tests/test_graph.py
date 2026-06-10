import json
from pathlib import Path

from pf2e_map_tracker.graph import (
    ANCHOR_NODE_MASS,
    ANCHOR_SPRING_LENGTH,
    UNKNOWN_ROOM_COLOR,
    UNKNOWN_ROOM_NAME,
    build_network,
    generate_graph,
)
from pf2e_map_tracker.html_enhancements import INJECTION_MARKER, inject_enhancements
from pf2e_map_tracker.io import load_map_data
from pf2e_map_tracker.models import Character, MapData, Room
from pf2e_map_tracker.tooltips import character_tooltip, room_tooltips

TEST_DATA = Path("tests/fixtures/test_data.json")


def test_build_network_contains_all_nodes_and_edges() -> None:
    data = load_map_data(TEST_DATA)
    network = build_network(data)

    assert len(network.nodes) == len(data.rooms) + len(data.characters) + len(data.character_groups)
    expected_placement_edges = len(data.characters) + len(data.character_groups)
    expected_anchor_edges = len([room for room in data.rooms if room.anchor])
    assert len(network.edges) == (
        len(data.connections) + expected_placement_edges + expected_anchor_edges
    )


def test_network_uses_ids_for_links_and_names_for_display() -> None:
    data = MapData.model_validate(
        {
            "rooms": [
                {"id": "source-room", "name": "Shared Name"},
                {"id": "target-room", "name": "Shared Name"},
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
            "rooms": [{"id": "room", "name": "Known Room"}],
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


def test_anchor_edges_override_spring_length() -> None:
    network = build_network(load_map_data(TEST_DATA))
    anchor_edges = [edge for edge in network.edges if edge.get("hidden")]

    assert anchor_edges
    assert all(edge["length"] == ANCHOR_SPRING_LENGTH for edge in anchor_edges)


def test_anchor_nodes_have_stronger_repulsion() -> None:
    data = load_map_data(TEST_DATA)
    network = build_network(data)
    nodes = {node["id"]: node for node in network.nodes}
    anchor_ids = {room.id for room in data.rooms if room.anchor}
    non_anchor_ids = {room.id for room in data.rooms if not room.anchor}

    assert anchor_ids
    assert all(nodes[node_id]["mass"] == ANCHOR_NODE_MASS for node_id in anchor_ids)
    assert all("mass" not in nodes[node_id] for node_id in non_anchor_ids)


def test_generate_graph_injects_enhancements_once(tmp_path: Path) -> None:
    output = generate_graph(TEST_DATA, tmp_path / "nested" / "map.html")
    inject_enhancements(output)

    content = output.read_text(encoding="utf-8")
    assert content.count(INJECTION_MARKER) == 1
    assert "setupCharacterVisibility" in content
    assert "setupNodeSelectorLabels" in content
    assert "Valeros" in content


def test_trusted_html_is_preserved_in_tooltips() -> None:
    character = Character(
        name="Merisiel",
        ancestry="Elf",
        location="kitchen",
        other_details="<b>trusted</b>",
    )
    room = Room(id="kitchen", name="Kitchen", notes="<p>trusted</p>")

    assert "<b>trusted</b>" in character_tooltip(character, "Kitchen")
    assert "<p>trusted</p>" in room_tooltips(room, [], [])[0]


def test_node_shape_overrides_are_added_to_network() -> None:
    data = MapData.model_validate(
        {
            "rooms": [{"id": "room", "name": "Room", "shape": "star"}],
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
            {"id": "room-castle", "name": "Room 🏰", "notes": "Notes 📝"},
            {"id": "other-room", "name": "Other Room 🚪"},
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
