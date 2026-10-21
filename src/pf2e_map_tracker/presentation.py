"""Source-backed details and compact image previews shared by both graph surfaces."""

from collections.abc import Callable
from html import escape

from pyvis.network import Network

from pf2e_map_tracker.models import UNKNOWN_ROOM_ID, MapData

TOOLTIP_PROPERTIES = ("title", "tooltip_hidden", "tooltip_groups_only", "tooltip_show_all")


def enrich_network(network: Network, data: MapData) -> None:
    rooms = {room.id: room.name for room in data.rooms}
    rooms[UNKNOWN_ROOM_ID] = "Unknown Room"
    groups = {group.id: group.name for group in data.character_groups}
    statuses = {status.id: status for status in data.connection_statuses}
    sources = {room.id: ("room", room) for room in data.rooms}
    sources.update({group.id: ("character_group", group) for group in data.character_groups})
    sources.update(
        {
            f"__character-{i}": ("character", character)
            for i, character in enumerate(data.characters)
        }
    )
    for index, connection in enumerate(data.connections):
        for side in ("source", "target"):
            sources[f"__unknown-{index}-{side}"] = ("connection", connection)

    def detail(kind, item, appearance, title):
        fields = item.model_dump(mode="json", by_alias=True)
        references = {}
        for key in ("location", "from", "to"):
            if fields.get(key):
                references[key] = rooms[fields[key]]
        if fields.get("group"):
            references["group"] = groups[fields["group"]]
        result = {
            "kind": kind,
            "title": title,
            "fields": fields,
            "references": references,
            "appearance": appearance,
            "images": [{**image.model_dump(), "url": image.src} for image in item.images],
        }
        if kind == "connection":
            result["statusInfo"] = statuses[item.status].model_dump(mode="json")
            references["status"] = statuses[item.status].description
        if kind == "character_group":
            result["members"] = sorted(c.name for c in data.characters if c.group == item.id)
        if kind == "room":
            result["occupants"] = sorted(
                [c.name for c in data.characters if c.location == item.id]
                + [g.name for g in data.character_groups if g.location == item.id]
            )
        return result

    for node in network.nodes:
        kind, item = sources[node["id"]]
        node["detail"] = detail(
            kind, item, {"color": node["color"], "shape": node["shape"]}, node["label"]
        )
    nodes = {node["id"]: node for node in network.nodes}
    for index, edge in enumerate(network.edges):
        if index < len(data.connections):
            connection = data.connections[index]
            edge["id"] = f"__connection-{index}"
            edge["detail"] = detail(
                "connection",
                connection,
                {
                    "color": edge["color"],
                    "line_style": "dashed" if edge["dashes"] else "solid",
                    "direction": connection.direction,
                },
                connection.name or f"{rooms[connection.source]} — {rooms[connection.target]}",
            )
        else:
            owner = nodes[edge["from"]]
            edge["detail"] = owner["detail"]
            edge["title"] = owner["title"]
    for obj in [*network.nodes, *network.edges]:
        images = obj["detail"]["images"]
        if images:
            for key in TOOLTIP_PROPERTIES:
                if obj.get(key):
                    obj[key] = image_tooltip(obj[key], images)


def image_tooltip(text: str, images: list[dict]) -> str:
    image = images[0]
    count = f"<span>+{len(images) - 1} more</span>" if len(images) > 1 else ""
    return (
        '<div class="pf2e-tooltip-content" style="display:flex;gap:12px;align-items:flex-start">'
        f'<div style="min-width:0;overflow-wrap:anywhere">{text}</div>'
        '<div style="flex:0 0 112px;display:grid;gap:4px;text-align:center;font-size:12px">'
        f'<img class="pf2e-tooltip-image" src="{escape(image["url"], quote=True)}" '
        f'alt="{escape(image["alt"] or "Image preview", quote=True)}" '
        'style="width:112px;height:112px;object-fit:contain;border-radius:4px">'
        f"{count}</div></div>"
    )


def resolve_network_images(network: Network, resolve: Callable[[str], str]) -> None:
    for obj in [*network.nodes, *network.edges]:
        for image in obj["detail"]["images"]:
            source, url = image["src"], resolve(image["src"])
            image["url"] = url
            if source != url:
                for key in TOOLTIP_PROPERTIES:
                    if obj.get(key):
                        obj[key] = obj[key].replace(
                            f'src="{escape(source, quote=True)}"',
                            f'src="{escape(url, quote=True)}"',
                        )
