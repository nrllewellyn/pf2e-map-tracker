import json
from typing import Dict, Any, List
from pyvis.network import Network

ARROW_CONFIG: Dict[str, Dict[str, Any]] = {
    "forward_only": {
        "to": {"enabled": True, "scaleFactor": 0.6},
        "from": {"enabled": False}
    },
    "backward_only": {
        "to": {"enabled": False},
        "from": {"enabled": True, "scaleFactor": 0.6}
    },
    "bidirectional": {
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
Default direction when not specified in JSON: 'bidirectional'.
"""


def create_room_graph(json_file_path: str, output_html: str = "room_graph.html") -> None:
    """
    Generate an interactive directed graph of rooms and connections from a JSON file.

    The graph is created using PyVis and saved as a standalone HTML file that can be
    opened in any modern web browser. Nodes represent rooms; directed edges represent
    connections with configurable arrow directions and styling based on status.
    """
    data = _load_json(json_file_path)
    rooms = data.get("rooms", [])
    connections = data.get("connections", [])
    status_config = {s["name"]: s for s in data.get("connectionStatus", [])}

    net = _create_network_instance()

    _add_nodes(net, rooms)
    _add_edges(net, connections, status_config)

    _configure_physics_and_style(net)

    net.write_html(output_html, notebook=False)
    print(f"Graph saved to: {output_html}")


def _load_json(file_path: str) -> dict:
    """Load and parse a JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _create_network_instance() -> Network:
    """Create a PyVis Network instance with default visual settings."""
    return Network(
        height="750px",
        width="100%",
        directed=True,
        bgcolor="#222222",
        font_color="white",
        notebook=False,
        select_menu=True,
        filter_menu=False,
        cdn_resources='remote'
    )


def _add_nodes(net: Network, rooms: List[dict]) -> None:
    """Add room nodes to the network."""
    for curr_room in rooms:
        name = curr_room.get("name", "Unnamed")
        color = curr_room.get("color", "#97c2fc")
        notes = curr_room.get("notes", "")

        tooltip = name
        if notes:
            tooltip += f"\n\nNotes:\n{notes}"

        net.add_node(
            name,
            label=name,
            title=tooltip,
            color=color,
            shape="box",
            font={"size": 16}
        )


def _add_edges(net: Network, connections: List[dict], status_config: Dict[str, dict]) -> None:
    """Add all directed edges to the network."""
    for curr_connection in connections:
        _add_single_edge(net, curr_connection, status_config)


def _add_single_edge(network: Network, connection: dict, status_config: Dict[str, dict]) -> None:
    """
    Add one directed edge to the network, including validation, direction handling,
    tooltip construction, and visual styling.
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

    # Determine direction (default: bidirectional)
    direction = connection.get("direction", "bidirectional").lower()
    if direction not in ARROW_CONFIG:
        print(f"Warning: Invalid direction '{direction}' in {from_room} → {to_room}. "
              f"Defaulting to 'bidirectional'.")
        direction = "bidirectional"

    arrows = ARROW_CONFIG[direction]

    # Build tooltip
    tooltip_parts = []
    if name := connection.get("name"):
        tooltip_parts.append(f"Name: {name}")
    tooltip_parts.append(f"Status: {description}")
    tooltip_parts.append(f"From: {from_room}")
    tooltip_parts.append(f"To: {to_room}")
    if notes := connection.get("notes"):
        tooltip_parts.append(f"\nNotes:\n{notes}")

    tooltip = "\n".join(tooltip_parts)

    # Edge appearance
    is_dashed = status.get("line_style", "solid") == "dashed"
    color = status.get("display_color", "#aaaaaa")

    network.add_edge(
        from_room,
        to_room,
        title=tooltip,
        color=color,
        dashes=is_dashed,
        width=2.5,
        arrows=arrows
    )


def _configure_physics_and_style(net: Network) -> None:
    """Apply physics simulation and global styling overrides."""

    # Add this into the options below for on-screen physics controls
    # "configure": {
    #     "enabled": true,
    #     "filter": "physics"
    # },

    net.set_options("""
    {
      "layout": {
        "randomSeed": 42
      },
      "interaction": {
        "zoomView": true,
        "dragView": true,
        "keyboard": true
      },
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -5000,
          "centralGravity": 0.15,
          "springLength": 140,
          "springConstant": 0.08,
          "damping": 0.55,
          "avoidOverlap": 0.7
        },
        "minVelocity": 0.05,
        "solver": "barnesHut",
        "stabilization": {
          "enabled": true,
          "iterations": 3000,
          "updateInterval": 25,
          "onlyDynamicEdges": false
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
          "to":   {"scaleFactor": 0.6},
          "from": {"scaleFactor": 0.6}
        },
        "smooth": {
          "type": "continuous"
        }
      }
    }
    """)
