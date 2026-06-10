import json
from enum import StrEnum
from typing import Dict, Any, List

from pyvis.network import Network


class ConnectionDirection(StrEnum):
    FORWARD_ONLY = "forward_only"
    BACKWARD_ONLY = "backward_only"
    BIDIRECTIONAL = "bidirectional"


ARROW_CONFIG: Dict[str, Dict[str, Any]] = {
    ConnectionDirection.FORWARD_ONLY: {
        "to": {"enabled": True, "scaleFactor": 0.6},
        "from": {"enabled": False}
    },
    ConnectionDirection.BACKWARD_ONLY: {
        "to": {"enabled": False},
        "from": {"enabled": True, "scaleFactor": 0.6}
    },
    ConnectionDirection.BIDIRECTIONAL: {
        "to": {"enabled": True, "scaleFactor": 0.6},
        "from": {"enabled": True, "scaleFactor": 0.6}
    },
}
"""
Mapping of direction strings to PyVis arrow configurations.

Supported values:
    - 'forward_only'     : arrow only on the 'to' side
    - 'backward_only'    : arrow only on the 'from' side
    - 'bidirectional'    : arrows on both sides

The 'scaleFactor' controls arrow head size (smaller value = less prominent arrows).
Default direction: 'bidirectional'.
"""

DEFAULT_ROOM_COLOR = "#3175cf"
DEFAULT_CHARACTER_COLOR = "#9c27b0"
DEFAULT_CHARACTER_GROUP_COLOR = "#00a896"
DEFAULT_CONNECTION_COLOR = "#aaaaaa"
REQUIRED_CHARACTER_FIELDS = ("name", "ancestry")
OPTIONAL_CHARACTER_FIELDS = (
    "class",
    "physical_description",
    "personality",
    "other_details",
    "color"
)
REQUIRED_CHARACTER_GROUP_FIELDS = ("name", "location")


def create_room_graph(json_file_path: str, output_html: str = "room_graph.html") -> None:
    """
    Generate an interactive directed graph of rooms and connections from a JSON file.

    Nodes represent rooms; directed edges represent connections with configurable
    arrow directions and styling based on status. The result is saved as a standalone
    HTML file viewable in any modern browser.
    """
    data = _load_json(json_file_path)
    rooms = data.get("rooms", [])
    characters = data.get("characters", [])
    character_groups = data.get("character_groups", [])
    connections = data.get("connections", [])
    status_config = {s["name"]: s for s in data.get("connectionStatus", [])}

    _validate_graph_nodes(rooms, characters, character_groups)

    net = _create_network_instance()

    _add_nodes(net, rooms, character_groups, characters)
    _add_character_groups(net, character_groups, characters)
    _add_characters(net, characters)
    _add_edges(net, connections, status_config)
    _add_placement_edges(net, characters, character_groups)
    _add_anchor_edges(net, rooms)

    _configure_physics_and_style(net)

    net.write_html(output_html, notebook=False)
    _enable_html_tooltips(output_html)
    print(f"Graph saved to: {output_html}")


def _load_json(file_path: str) -> dict:
    """Load and parse the input JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _create_network_instance() -> Network:
    """Create a PyVis Network instance with default visual settings."""
    return Network(
        height="90vh",
        width="100%",
        directed=True,
        bgcolor="#222222",
        font_color="white",
        notebook=False,
        select_menu=True,
        filter_menu=False,
        cdn_resources='remote'
    )


def _add_nodes(
        net: Network,
        rooms: List[dict],
        character_groups: List[dict],
        characters: List[dict]
) -> None:
    """Add all room nodes to the network."""
    groups_by_room = {room["name"]: [] for room in rooms}
    direct_characters_by_room = {room["name"]: [] for room in rooms}
    members_by_group = {group["name"]: [] for group in character_groups}

    for character_group in character_groups:
        groups_by_room[character_group["location"]].append(character_group["name"])

    for character in characters:
        if group := character.get("group"):
            members_by_group[group].append(character["name"])
        else:
            direct_characters_by_room[character["location"]].append(character["name"])

    for room in rooms:
        _add_single_node(
            net,
            room,
            groups_by_room[room["name"]],
            direct_characters_by_room[room["name"]],
            members_by_group
        )


def _add_single_node(
        net: Network,
        room: dict,
        group_names: List[str],
        direct_character_names: List[str],
        members_by_group: Dict[str, List[str]]
) -> None:
    """Add a single room node with formatted HTML tooltip."""
    name = room.get("name")
    color = room.get("color", DEFAULT_ROOM_COLOR)
    notes = room.get("notes", "")

    if not name:
        raise ValueError("Missing room name")

    tooltip_parts = [f"<b>{name}</b>"]

    if notes:
        formatted_notes = notes.replace("\n", "<br>")
        tooltip_parts.append(f"<br><br><b>Notes:</b><br>{formatted_notes}")

    base_tooltip_html = "".join(tooltip_parts)
    hidden_tooltip_parts = [base_tooltip_html]
    groups_only_tooltip_parts = [base_tooltip_html]

    if group_names or direct_character_names:
        hidden_tooltip_parts.append("<br><br><b>Characters:</b>")
        for group_name in sorted(group_names):
            hidden_tooltip_parts.append(f"<br>- {group_name}")
            for member_name in sorted(members_by_group[group_name]):
                hidden_tooltip_parts.append(f"<br>&nbsp;&nbsp;&nbsp;&nbsp;- {member_name}")
        for character_name in sorted(direct_character_names):
            hidden_tooltip_parts.append(f"<br>- {character_name}")

    if direct_character_names:
        groups_only_tooltip_parts.append("<br><br><b>Characters:</b>")
        for character_name in sorted(direct_character_names):
            groups_only_tooltip_parts.append(f"<br>- {character_name}")

    hidden_tooltip_html = "".join(hidden_tooltip_parts)
    groups_only_tooltip_html = "".join(groups_only_tooltip_parts)

    net.add_node(
        name,
        label=name,
        title=base_tooltip_html,
        color=color,
        shape="box",
        font={"size": 16},
        node_type="room",
        tooltip_hidden=hidden_tooltip_html,
        tooltip_groups_only=groups_only_tooltip_html,
        tooltip_show_all=base_tooltip_html
    )


def _validate_graph_nodes(
        rooms: List[dict],
        characters: List[dict],
        character_groups: List[dict]
) -> None:
    """Validate rooms, characters, groups, and their placement relationships."""
    room_names = set()

    for room in rooms:
        name = room.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Missing room name")
        if name in room_names:
            raise ValueError(f"Duplicate node name '{name}'")
        anchor = room.get("anchor")
        if anchor is not None and not isinstance(anchor, bool):
            raise ValueError(f"Optional field 'anchor' must be a boolean for room '{name}'")
        room_names.add(name)

    node_names = set(room_names)
    character_group_names = set()
    for character_group in character_groups:
        for field in REQUIRED_CHARACTER_GROUP_FIELDS:
            value = character_group.get(field)
            if not isinstance(value, str) or not value.strip():
                group_name = character_group.get("name", "<unnamed>")
                raise ValueError(
                    f"Missing or empty required field '{field}' for character group '{group_name}'"
                )

        color = character_group.get("color")
        if color is not None and not isinstance(color, str):
            raise ValueError(
                f"Optional field 'color' must be a string for character group "
                f"'{character_group['name']}'"
            )

        name = character_group["name"]
        if name in node_names:
            raise ValueError(f"Duplicate node name '{name}'")
        node_names.add(name)
        character_group_names.add(name)

        location = character_group["location"]
        if location not in room_names:
            raise ValueError(f"Unknown location '{location}' for character group '{name}'")

    for character in characters:
        for field in REQUIRED_CHARACTER_FIELDS:
            value = character.get(field)
            if not isinstance(value, str) or not value.strip():
                character_name = character.get("name", "<unnamed>")
                raise ValueError(
                    f"Missing or empty required field '{field}' for character '{character_name}'"
                )

        for field in OPTIONAL_CHARACTER_FIELDS:
            value = character.get(field)
            if value is not None and not isinstance(value, str):
                character_name = character.get("name", "<unnamed>")
                raise ValueError(
                    f"Optional field '{field}' must be a string for character '{character_name}'"
                )

        name = character["name"]
        if name in node_names:
            raise ValueError(f"Duplicate node name '{name}'")
        node_names.add(name)

        location = character.get("location")
        group = character.get("group")
        has_location = isinstance(location, str) and bool(location.strip())
        has_group = isinstance(group, str) and bool(group.strip())
        if has_location == has_group:
            raise ValueError(
                f"Character '{name}' must have exactly one non-empty 'location' or 'group'"
            )
        if location is not None and not isinstance(location, str):
            raise ValueError(f"Character 'location' must be a string for character '{name}'")
        if group is not None and not isinstance(group, str):
            raise ValueError(f"Character 'group' must be a string for character '{name}'")
        if has_location and location not in room_names:
            raise ValueError(f"Unknown location '{location}' for character '{name}'")
        if has_group and group not in character_group_names:
            raise ValueError(f"Unknown group '{group}' for character '{name}'")


def _add_character_groups(
        net: Network,
        character_groups: List[dict],
        characters: List[dict]
) -> None:
    """Add all character-group nodes to the network."""
    members_by_group = {group["name"]: [] for group in character_groups}
    for character in characters:
        if group := character.get("group"):
            members_by_group[group].append(character["name"])

    for character_group in character_groups:
        _add_single_character_group(
            net,
            character_group,
            sorted(members_by_group[character_group["name"]])
        )


def _add_single_character_group(net: Network, character_group: dict, members: List[str]) -> None:
    """Add a character-group node with its location and members in the tooltip."""
    name = character_group["name"]
    location = character_group["location"]
    color = character_group.get("color", DEFAULT_CHARACTER_GROUP_COLOR)
    base_tooltip_html = (
        f"<b>{name}</b>"
        f"<br><br><b>Location:</b> {location}"
    )
    member_list = "<br>".join(members) if members else "None"
    groups_only_tooltip_html = (
        base_tooltip_html +
        f"<br><br><b>Members:</b><br>{member_list}"
    )

    net.add_node(
        name,
        label=name,
        title=base_tooltip_html,
        color=color,
        shape="circle",
        font={"size": 16},
        node_type="character_group",
        tooltip_hidden=base_tooltip_html,
        tooltip_groups_only=groups_only_tooltip_html,
        tooltip_show_all=base_tooltip_html
    )


def _add_characters(net: Network, characters: List[dict]) -> None:
    """Add all character nodes to the network."""
    for character in characters:
        _add_single_character(net, character)


def _add_single_character(net: Network, character: dict) -> None:
    """Add a character node with a formatted HTML tooltip."""
    name = character["name"]
    ancestry = character["ancestry"]
    color = character.get("color", DEFAULT_CHARACTER_COLOR)

    tooltip_html = (
        f"<b>{name}</b>"
        f"<br><br><b>Ancestry:</b> {ancestry}"
    )
    if character_class := character.get("class", ""):
        tooltip_html += f"<br><b>Class:</b> {character_class}"
    if location := character.get("location"):
        tooltip_html += f"<br><b>Location:</b> {location}"
    else:
        tooltip_html += f"<br><b>Group:</b> {character['group']}"

    detail_fields = (
        ("physical_description", "Physical Description"),
        ("personality", "Personality"),
        ("other_details", "Other Details")
    )
    for field, label in detail_fields:
        if detail := character.get(field, ""):
            formatted_detail = detail.replace("\n", "<br>")
            tooltip_html += f"<br><br><b>{label}:</b><br>{formatted_detail}"

    net.add_node(
        name,
        label=name,
        title=tooltip_html,
        color=color,
        shape="ellipse",
        font={"size": 16},
        node_type="character"
    )


def _add_edges(net: Network, connections: List[dict], status_config: Dict[str, dict]) -> None:
    """Add all directed edges to the network."""
    for connection in connections:
        _add_single_edge(net, connection, status_config)


def _add_single_edge(net: Network, connection: dict, status_config: Dict[str, dict]) -> None:
    """
    Add a single directed edge with validation, direction handling,
    HTML tooltip, and visual styling.
    """
    status_name = connection.get("status")
    if not status_name or status_name not in status_config:
        raise ValueError(f"Invalid or missing status '{status_name}' in connection")

    status = status_config[status_name]
    description = status.get("description")
    if not description:
        raise ValueError(f"Missing description for status '{status_name}'")

    from_room = connection.get("from")
    to_room = connection.get("to")
    if not from_room or not to_room:
        raise ValueError(f"Missing 'from' or 'to' in connection: {connection}")

    # Resolve direction with fallback
    direction_str = connection.get("direction", ConnectionDirection.BIDIRECTIONAL).lower()
    try:
        direction = ConnectionDirection(direction_str)
    except ValueError:
        print(f"Warning: Invalid direction '{direction_str}' in {from_room} → {to_room}. "
              f"Defaulting to '{ConnectionDirection.BIDIRECTIONAL}'.")
        direction = ConnectionDirection.BIDIRECTIONAL

    arrows = ARROW_CONFIG[direction]

    # Build HTML tooltip
    tooltip_parts = []
    if name := connection.get("name"):
        tooltip_parts.append(f"<b>{name}</b>")
    tooltip_parts.append(f"<b>Status:</b> {description}")

    if direction == ConnectionDirection.FORWARD_ONLY:
        tooltip_parts.append(f"<br>{from_room} 🡒 {to_room}")
    elif direction == ConnectionDirection.BACKWARD_ONLY:
        tooltip_parts.append(f"<br>{to_room} 🡒 {from_room}")
    else:
        tooltip_parts.append(f"<br>{from_room} 🡘 {to_room}")

    if notes := connection.get("notes"):
        formatted_notes = notes.replace("\n", "<br>")
        tooltip_parts.append(f"<br><b>Notes:</b><br>{formatted_notes}")

    tooltip_html = "<br>".join(tooltip_parts)

    # Edge appearance
    is_dashed = status.get("line_style", "solid") == "dashed"
    color = status.get("display_color", DEFAULT_CONNECTION_COLOR)

    net.add_edge(
        from_room,
        to_room,
        title=tooltip_html,
        color=color,
        dashes=is_dashed,
        width=2.5,
        arrows=arrows
    )


def _add_placement_edges(
        net: Network,
        characters: List[dict],
        character_groups: List[dict]
) -> None:
    """Connect characters to their placement target and groups to their rooms."""
    for character in characters:
        target = character.get("location") or character["group"]
        _add_placement_edge(net, character["name"], target)

    for character_group in character_groups:
        _add_placement_edge(net, character_group["name"], character_group["location"])


def _add_placement_edge(net: Network, source: str, target: str) -> None:
    """Add a dashed, neutral, arrowless placement edge."""
    net.add_edge(
        source,
        target,
        color=DEFAULT_CONNECTION_COLOR,
        dashes=True,
        width=2.5,
        arrows={
            "to": {"enabled": False},
            "from": {"enabled": False}
        }
    )


def _add_anchor_edges(net: Network, rooms: List[dict]) -> None:
    """Connect anchor rooms with invisible edges that participate in physics."""
    anchor_names = [room["name"] for room in rooms if room.get("anchor", False)]

    if len(anchor_names) < 2:
        return

    edge_count = 1 if len(anchor_names) == 2 else len(anchor_names)
    for index in range(edge_count):
        net.add_edge(
            anchor_names[index],
            anchor_names[(index + 1) % len(anchor_names)],
            hidden=True,
            physics=True,
            arrows={
                "to": {"enabled": False},
                "from": {"enabled": False}
            }
        )


def _configure_physics_and_style(net: Network) -> None:
    """Apply physics simulation and global styling overrides."""

    options_dict = {
        "layout": {
            "randomSeed": 42
        },
        "interaction": {
            "zoomView": True,
            "dragView": True,
            "keyboard": True,
            "hover": True,
            "hideEdgesOnDrag": False,
            "hideNodesOnDrag": False,
            "tooltipDelay": 999999,  # Extremely long delay to disable built-in tooltips (since we are using custom ones)
        },
        "physics": {
            "enabled": True,
            "barnesHut": {
                "gravitationalConstant": -8000,
                "centralGravity": 0.15,
                "springLength": 200,
                "springConstant": 0.08,
                "damping": 0.55,
                "avoidOverlap": 0.7
            },
            "minVelocity": 1.00,
            "solver": "barnesHut",
            "stabilization": {
                "enabled": True,
                "iterations": 3000,
                "updateInterval": 25,
                "onlyDynamicEdges": False
            }
        },
        "nodes": {
            "shape": "box",
            "margin": 12,
            "scaling": {
                "min": 25,
                "max": 50
            }
        },
        "edges": {
            "arrows": {
                "to": {"scaleFactor": 0.6},
                "from": {"scaleFactor": 0.6}
            },
            "smooth": {
                "type": "continuous"
            }
        }
    }

    net.set_options(json.dumps(options_dict))


def _enable_html_tooltips(html_file_path: str) -> None:
    """Post-process the generated HTML to inject custom HTML tooltip support."""
    with open(html_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    injection = r"""
<script>
// Create a single reusable tooltip div
const tooltip = document.createElement('div');
tooltip.id = 'custom-vis-tooltip';
tooltip.style.position = 'absolute';
tooltip.style.visibility = 'hidden';
tooltip.style.padding = '8px 12px';
tooltip.style.backgroundColor = 'rgba(30, 30, 50, 0.96)';
tooltip.style.color = '#f0f0ff';
tooltip.style.border = '1px solid #666';
tooltip.style.borderRadius = '6px';
tooltip.style.maxWidth = '420px';
tooltip.style.fontSize = '13px';
tooltip.style.lineHeight = '1.5';
tooltip.style.pointerEvents = 'none';
tooltip.style.zIndex = '9999';
tooltip.style.boxShadow = '0 4px 12px rgba(0,0,0,0.4)';
document.body.appendChild(tooltip);

function showTooltip(event, htmlContent, x, y) {
  if (!htmlContent) {
    tooltip.style.visibility = 'hidden';
    return;
  }
  tooltip.innerHTML = htmlContent.replace(/\n/g, '<br>');
  tooltip.style.left = (x + 20) + 'px';
  tooltip.style.top  = (y + 20) + 'px';
  tooltip.style.visibility = 'visible';
}

function hideTooltip() {
  tooltip.style.visibility = 'hidden';
}

function setCharacterVisibility(visibility) {
  const tooltipProperty = 'tooltip_' + visibility;
  const updatedNodes = nodes.get().map(function(node) {
    if (node.node_type === 'character') {
      return { id: node.id, hidden: visibility !== 'show_all' };
    }
    if (node.node_type === 'character_group') {
      return {
        id: node.id,
        hidden: visibility === 'hidden',
        title: node[tooltipProperty]
      };
    }
    if (node.node_type === 'room') {
      return {
        id: node.id,
        hidden: false,
        title: node[tooltipProperty]
      };
    }
    return { id: node.id, hidden: false };
  });

  hideTooltip();
  nodes.update(updatedNodes);
}

function setupCharacterVisibility() {
  if (!window.network || !window.nodes) {
    setTimeout(setupCharacterVisibility, 100);
    return;
  }

  const selectMenu = document.getElementById('select-menu');
  if (!selectMenu || document.getElementById('character-visibility')) {
    return;
  }

  const controlRow = document.createElement('div');
  controlRow.className = 'row no-gutters';
  controlRow.innerHTML = `
    <div class="col-12 pb-2" style="max-width: 320px;">
      <label for="character-visibility" class="form-label mb-1">Character Visibility</label>
      <select id="character-visibility" class="form-select" aria-label="Character Visibility">
        <option value="hidden">Hidden</option>
        <option value="groups_only" selected>Groups Only</option>
        <option value="show_all">Show All</option>
      </select>
    </div>`;
  selectMenu.prepend(controlRow);

  const visibilitySelect = document.getElementById('character-visibility');
  visibilitySelect.addEventListener('change', function(event) {
    setCharacterVisibility(event.target.value);
  });
  setCharacterVisibility(visibilitySelect.value);
}

function setupCustomTooltips() {
  if (!window.network) {
    setTimeout(setupCustomTooltips, 100);
    return;
  }

  console.log('Custom HTML tooltips initialized');

  network.on('hoverNode', function(params) {
    const node = network.body.nodes[params.node];
    if (node?.options?.title) {
      showTooltip(params.event, node.options.title, params.event.pageX, params.event.pageY);
    }
  });

  network.on('blurNode', hideTooltip);

  network.on('hoverEdge', function(params) {
    const edge = network.body.edges[params.edge];
    if (edge?.options?.title) {
      showTooltip(params.event, edge.options.title, params.event.pageX, params.event.pageY);
    }
  });

  network.on('blurEdge', hideTooltip);
}

if (document.readyState === 'complete') {
  setupCustomTooltips();
  setupCharacterVisibility();
} else {
  document.addEventListener('DOMContentLoaded', setupCustomTooltips);
  document.addEventListener('DOMContentLoaded', setupCharacterVisibility);
}
</script>"""

    # Insert before </body>
    if '</body>' in content.lower():
        parts = content.rsplit('</body>', 1)
        content = parts[0] + injection + '</body>' + (parts[1] if len(parts) > 1 else '')
    else:
        content += injection

    with open(html_file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Injected custom HTML tooltip overlay into {html_file_path}")
