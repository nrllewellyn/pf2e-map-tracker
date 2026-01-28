import json
from pyvis.network import Network


def create_room_graph(json_file_path, output_html="room_graph.html"):
    """
    Reads room and connection data from JSON and creates an interactive graph with PyVis
    """
    # Load the JSON data
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Extract sections with safe defaults
    rooms = data.get("rooms", [])
    connections = data.get("connections", [])
    status_config = {s["name"]: s for s in data.get("connectionStatus", [])}

    # Create pyvis network (directed by default - change to False if undirected)
    net = Network(
        height="750px",
        width="100%",
        directed=True,
        bgcolor="#222222",
        font_color="white",
        notebook=False,  # set to True if using in Jupyter
        select_menu=True,
        filter_menu=False,
        cdn_resources='remote'
    )

    # Add room nodes
    for room in rooms:
        name = room.get("name", "Unnamed")
        color = room.get("color", "#97c2fc")  # default nice blue
        notes = room.get("notes", "")

        tooltip = f"{name}\n"
        if notes:
            tooltip += f"\nNotes:\n{notes}"

        net.add_node(
            name,  # using name as unique identifier
            label=name,
            title=tooltip,
            color=color,
            shape="box",
            font={"size": 16}
        )

    # Add connections (edges)
    for connection in connections:
        # Required fields
        status_name = connection.get("status")
        if not status_name or status_name not in status_config:
            raise ValueError(f"Invalid/missing status '{status_name}' in connection")

        # Get config for this status
        status = status_config[status_name]
        status_description = status.get("description", "")
        if not status_description:
            raise ValueError(f"Warning: Missing description for status {status_name}")

        # Get from/to rooms
        from_room = connection.get("from")
        to_room = connection.get("to")

        # Get edge line style
        is_line_dashed = status.get("line_style", "solid") == "dashed"

        if not from_room or not to_room:
            raise ValueError(f"Warning: Missing from/to in connection: {connection}")

        # Optional fields
        connection_name = connection.get("name", "")
        connection_notes = connection.get("notes", "")

        # Build tooltip for edge
        tooltip = ""
        if connection_name:
            tooltip += f"Name: {connection_name}\n"
        tooltip += f"Status: {status_description}\n"
        tooltip += f"From: {from_room}\nTo: {to_room}\n"
        if connection_notes:
            tooltip += f"\nNotes:\n{connection_notes}"

        # Edge color from status
        edge_color = status.get("display_color", "#aaaaaa")

        net.add_edge(
            from_room,
            to_room,
            title=tooltip,
            color=edge_color,
            dashes=is_line_dashed,
            width=2.5,
            arrows={'to': {'enabled': True, 'scaleFactor': 0.8}}
        )

    # Some nice physics settings for better layout
    net.barnes_hut(
        gravity=-3500,
        central_gravity=0.2,
        spring_length=180,
        spring_strength=0.05,
        damping=0.09
    )

    # Optional: make nodes a bit bigger and more readable
    net.set_options("""
    {
      "nodes": {
        "shape": "box",
        "margin": 10,
        "scaling": {
          "min": 20,
          "max": 45
        }
      },
      "edges": {
        "arrows": {
          "to": {
            "enabled": true,
            "scaleFactor": 0.8
          }
        },
        "smooth": {
          "type": "continuous"
        }
      }
    }
    """)

    # Write to HTML file
    net.write_html(output_html, notebook=False)
    print(f"Graph saved to: {output_html}")
