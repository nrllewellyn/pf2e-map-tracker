"""Build and write the interactive PyVis graph."""

import json
from pathlib import Path

from pyvis.network import Network

from pf2e_map_tracker.html_enhancements import inject_enhancements
from pf2e_map_tracker.io import load_graph_options, load_map_data
from pf2e_map_tracker.models import ConnectionDirection, MapData
from pf2e_map_tracker.tooltips import (
    character_group_tooltips,
    character_tooltip,
    connection_tooltip,
    room_tooltips,
)

DEFAULT_ROOM_COLOR = "#3175cf"
DEFAULT_CHARACTER_COLOR = "#9c27b0"
DEFAULT_CHARACTER_GROUP_COLOR = "#00a896"
DEFAULT_CONNECTION_COLOR = "#aaaaaa"
ANCHOR_SPRING_LENGTH = 400
ANCHOR_NODE_MASS = 4

ARROW_CONFIG = {
    ConnectionDirection.FORWARD_ONLY: {
        "to": {"enabled": True, "scaleFactor": 0.6},
        "from": {"enabled": False},
    },
    ConnectionDirection.BACKWARD_ONLY: {
        "to": {"enabled": False},
        "from": {"enabled": True, "scaleFactor": 0.6},
    },
    ConnectionDirection.BIDIRECTIONAL: {
        "to": {"enabled": True, "scaleFactor": 0.6},
        "from": {"enabled": True, "scaleFactor": 0.6},
    },
}
NO_ARROWS = {"to": {"enabled": False}, "from": {"enabled": False}}


def generate_graph(input_path: Path, output_path: Path) -> Path:
    data = load_map_data(input_path)
    network = build_network(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(network.generate_html(notebook=False), encoding="utf-8")
    inject_enhancements(output_path)
    return output_path


def build_network(data: MapData) -> Network:
    network = Network(
        height="90vh",
        width="100%",
        directed=True,
        bgcolor="#222222",
        font_color="white",
        notebook=False,
        select_menu=True,
        filter_menu=False,
        cdn_resources="remote",
    )
    network.templateEnv.policies["json.dumps_kwargs"] = {
        **network.templateEnv.policies["json.dumps_kwargs"],
        "ensure_ascii": False,
    }
    _add_rooms(network, data)
    _add_character_groups(network, data)
    _add_characters(network, data)
    _add_connections(network, data)
    _add_placement_edges(network, data)
    _add_anchor_edges(network, data)
    options = load_graph_options().model_dump(by_alias=True)
    network.set_options(json.dumps(options))
    return network


def _add_rooms(network: Network, data: MapData) -> None:
    groups_by_room = {room.id: [] for room in data.rooms}
    direct_characters_by_room = {room.id: [] for room in data.rooms}
    members_by_group = {group.id: [] for group in data.character_groups}

    for group in data.character_groups:
        groups_by_room[group.location].append(group)
    for character in data.characters:
        if character.group:
            members_by_group[character.group].append(character.name)
        else:
            direct_characters_by_room[character.location].append(character.name)

    for room in data.rooms:
        base, hidden, groups_only = room_tooltips(
            room,
            [(group.name, members_by_group[group.id]) for group in groups_by_room[room.id]],
            direct_characters_by_room[room.id],
        )
        network.add_node(
            room.id,
            label=room.name,
            title=base,
            color=room.color or DEFAULT_ROOM_COLOR,
            shape=room.shape,
            font={"size": 16},
            node_type="room",
            **({"mass": ANCHOR_NODE_MASS} if room.anchor else {}),
            tooltip_hidden=hidden,
            tooltip_groups_only=groups_only,
            tooltip_show_all=base,
        )


def _add_character_groups(network: Network, data: MapData) -> None:
    rooms_by_id = {room.id: room for room in data.rooms}
    members_by_group = {group.id: [] for group in data.character_groups}
    for character in data.characters:
        if character.group:
            members_by_group[character.group].append(character.name)

    for group in data.character_groups:
        base, groups_only = character_group_tooltips(
            group,
            rooms_by_id[group.location].name,
            sorted(members_by_group[group.id]),
        )
        network.add_node(
            group.id,
            label=group.name,
            title=base,
            color=group.color or DEFAULT_CHARACTER_GROUP_COLOR,
            shape=group.shape,
            font={"size": 16},
            node_type="character_group",
            tooltip_hidden=base,
            tooltip_groups_only=groups_only,
            tooltip_show_all=base,
        )


def _add_characters(network: Network, data: MapData) -> None:
    rooms_by_id = {room.id: room for room in data.rooms}
    groups_by_id = {group.id: group for group in data.character_groups}
    for index, character in enumerate(data.characters):
        placement_name = (
            rooms_by_id[character.location].name
            if character.location
            else groups_by_id[character.group].name
        )
        network.add_node(
            _character_node_id(index),
            label=character.name,
            title=character_tooltip(character, placement_name),
            color=character.color or DEFAULT_CHARACTER_COLOR,
            shape=character.shape,
            font={"size": 16},
            node_type="character",
        )


def _add_connections(network: Network, data: MapData) -> None:
    rooms = {room.id: room for room in data.rooms}
    statuses = {status.id: status for status in data.connection_statuses}
    for connection in data.connections:
        status = statuses[connection.status]
        network.add_edge(
            connection.source,
            connection.target,
            title=connection_tooltip(
                connection,
                status,
                rooms[connection.source].name,
                rooms[connection.target].name,
            ),
            color=status.display_color or DEFAULT_CONNECTION_COLOR,
            dashes=status.line_style == "dashed",
            width=2.5,
            arrows=ARROW_CONFIG[connection.direction],
        )


def _add_placement_edges(network: Network, data: MapData) -> None:
    for index, character in enumerate(data.characters):
        _add_placement_edge(
            network,
            _character_node_id(index),
            character.location or character.group,
        )
    for group in data.character_groups:
        _add_placement_edge(network, group.id, group.location)


def _add_placement_edge(network: Network, source: str, target: str) -> None:
    network.add_edge(
        source,
        target,
        color=DEFAULT_CONNECTION_COLOR,
        dashes=True,
        width=2.5,
        arrows=NO_ARROWS,
    )


def _character_node_id(index: int) -> str:
    return f"__character-{index}"


def _add_anchor_edges(network: Network, data: MapData) -> None:
    anchor_ids = [room.id for room in data.rooms if room.anchor]
    if len(anchor_ids) < 2:
        return

    edge_count = 1 if len(anchor_ids) == 2 else len(anchor_ids)
    for index in range(edge_count):
        network.add_edge(
            anchor_ids[index],
            anchor_ids[(index + 1) % len(anchor_ids)],
            hidden=True,
            physics=True,
            length=ANCHOR_SPRING_LENGTH,
            arrows=NO_ARROWS,
        )
