import json
from typing import Dict, Any, List

from pyvis.network import Network


class ConnectionDirection(str):
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

DEFAULT_ROOM_COLOR = "#97c2fc"
DEFAULT_CONNECTION_COLOR = "#aaaaaa"


def create_room_graph(json_file_path: str, output_html: str = "room_graph.html") -> None:
    """
    Generate an interactive directed graph of rooms and connections from a JSON file.

    Nodes represent rooms; directed edges represent connections with configurable
    arrow directions and styling based on status. The result is saved as a standalone
    HTML file viewable in any modern browser.
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
    _enable_html_tooltips(output_html)
    print(f"Graph saved to: {output_html}")


def _load_json(file_path: str) -> dict:
    """Load and parse the input JSON file."""
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
    """Add all room nodes to the network."""
    for room in rooms:
        _add_single_node(net, room)


def _add_single_node(net: Network, room: dict) -> None:
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

    tooltip_html = "".join(tooltip_parts)

    net.add_node(
        name,
        label=name,
        title=tooltip_html,
        color=color,
        shape="box",
        font={"size": 16}
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
            "tooltipDelay": 999999, # Extremely long delay to disable built-in tooltips (since we are using custom ones)
        },
        "physics": {
            "enabled": True,
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
} else {
  document.addEventListener('DOMContentLoaded', setupCustomTooltips);
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
