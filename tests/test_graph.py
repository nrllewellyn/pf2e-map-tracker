from pathlib import Path

from pf2e_map_tracker.graph import build_network, generate_graph
from pf2e_map_tracker.html_enhancements import INJECTION_MARKER, inject_enhancements
from pf2e_map_tracker.io import load_map_data
from pf2e_map_tracker.models import Character, Room
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
