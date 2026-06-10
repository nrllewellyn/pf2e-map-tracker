import json
from pathlib import Path

from pf2e_map_tracker.graph import build_network, generate_graph
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


def test_generate_graph_injects_enhancements_once(tmp_path: Path) -> None:
    output = generate_graph(TEST_DATA, tmp_path / "nested" / "map.html")
    inject_enhancements(output)

    content = output.read_text(encoding="utf-8")
    assert content.count(INJECTION_MARKER) == 1
    assert "setupCharacterVisibility" in content
    assert "Valeros" in content


def test_trusted_html_is_preserved_in_tooltips() -> None:
    character = Character(
        name="Merisiel",
        ancestry="Elf",
        location="Kitchen",
        other_details="<b>trusted</b>",
    )
    room = Room(name="Kitchen", notes="<p>trusted</p>")

    assert "<b>trusted</b>" in character_tooltip(character)
    assert "<p>trusted</p>" in room_tooltips(room, [], [], {})[0]


def test_node_shape_overrides_are_added_to_network() -> None:
    data = MapData.model_validate(
        {
            "rooms": [{"name": "Room", "shape": "star"}],
            "character_groups": [{"name": "Group", "location": "Room", "shape": "triangle"}],
            "characters": [
                {
                    "name": "Character",
                    "ancestry": "Human",
                    "group": "Group",
                    "shape": "diamond",
                }
            ],
        }
    )

    nodes = {node["id"]: node for node in build_network(data).nodes}

    assert nodes["Room"]["shape"] == "star"
    assert nodes["Group"]["shape"] == "triangle"
    assert nodes["Character"]["shape"] == "diamond"


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
            {"name": "Room 🏰", "notes": "Notes 📝"},
            {"name": "Other Room 🚪"},
        ],
        "character_groups": [{"name": "Party 🛡️", "location": "Room 🏰"}],
        "characters": [
            {
                "name": "Hero 🧙",
                "ancestry": "Elf 🧝",
                "class": "Wizard ✨",
                "physical_description": "Description 👀",
                "personality": "Personality 😀",
                "other_details": "Details 🔮",
                "group": "Party 🛡️",
            }
        ],
        "connections": [
            {
                "from": "Room 🏰",
                "to": "Other Room 🚪",
                "status": "Open ✅",
                "name": "Passage ↗️",
                "notes": "Connection notes 🧭",
            }
        ],
        "connectionStatus": [{"name": "Open ✅", "description": "Open door 🚶"}],
    }
    input_path = tmp_path / "emoji.json"
    output_path = tmp_path / "emoji.html"
    input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    loaded = load_map_data(input_path)
    generate_graph(input_path, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert loaded.connections[0].status == "Open ✅"
    assert all(value in content for value in emoji_values)
