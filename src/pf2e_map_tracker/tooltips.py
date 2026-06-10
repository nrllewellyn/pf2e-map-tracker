"""Trusted-HTML tooltip builders."""

from pf2e_map_tracker.models import Character, CharacterGroup, Connection, ConnectionStatus, Room


def room_tooltips(
    room: Room,
    group_members: list[tuple[str, list[str]]],
    direct_character_names: list[str],
) -> tuple[str, str, str]:
    parts = [f"<b>{room.name}</b>"]
    if room.notes:
        parts.append(f"<br><br><b>Notes:</b><br>{_format_multiline(room.notes)}")
    base = "".join(parts)

    hidden_parts = [base]
    groups_only_parts = [base]
    if group_members or direct_character_names:
        hidden_parts.append("<br><br><b>Characters:</b>")
        for group_name, member_names in sorted(group_members):
            hidden_parts.append(f"<br>- {group_name}")
            for member_name in sorted(member_names):
                hidden_parts.append(f"<br>&nbsp;&nbsp;&nbsp;&nbsp;- {member_name}")
        hidden_parts.extend(f"<br>- {name}" for name in sorted(direct_character_names))

    if direct_character_names:
        groups_only_parts.append("<br><br><b>Characters:</b>")
        groups_only_parts.extend(f"<br>- {name}" for name in sorted(direct_character_names))

    return base, "".join(hidden_parts), "".join(groups_only_parts)


def character_group_tooltips(
    group: CharacterGroup,
    location_name: str,
    members: list[str],
) -> tuple[str, str]:
    base = f"<b>{group.name}</b><br><br><b>Location:</b> {location_name}"
    member_list = "<br>".join(members) if members else "None"
    return base, f"{base}<br><br><b>Members:</b><br>{member_list}"


def character_tooltip(character: Character, placement_name: str) -> str:
    parts = [f"<b>{character.name}</b>", f"<br><br><b>Ancestry:</b> {character.ancestry}"]
    if character.class_name:
        parts.append(f"<br><b>Class:</b> {character.class_name}")
    if character.location:
        parts.append(f"<br><b>Location:</b> {placement_name}")
    else:
        parts.append(f"<br><b>Group:</b> {placement_name}")

    details = (
        (character.physical_description, "Physical Description"),
        (character.personality, "Personality"),
        (character.other_details, "Other Details"),
    )
    for value, label in details:
        if value:
            parts.append(f"<br><br><b>{label}:</b><br>{_format_multiline(value)}")
    return "".join(parts)


def connection_tooltip(
    connection: Connection,
    status: ConnectionStatus,
    source_name: str,
    target_name: str,
) -> str:
    parts: list[str] = []
    if connection.name:
        parts.append(f"<b>{connection.name}</b>")
    parts.append(f"<b>Status:</b> {status.description}")

    direction_symbol = {
        "forward_only": f"{source_name} 🡒 {target_name}",
        "backward_only": f"{target_name} 🡒 {source_name}",
        "bidirectional": f"{source_name} 🡘 {target_name}",
    }[connection.direction]
    parts.append(f"<br>{direction_symbol}")
    if connection.notes:
        parts.append(f"<br><b>Notes:</b><br>{_format_multiline(connection.notes)}")
    return "<br>".join(parts)


def _format_multiline(value: str) -> str:
    return value.replace("\n", "<br>")
