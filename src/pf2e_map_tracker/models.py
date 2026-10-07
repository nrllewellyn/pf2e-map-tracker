"""Typed input and graph-option models."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MapId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
UNKNOWN_ROOM_ID = "unknown"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ConnectionDirection(StrEnum):
    FORWARD_ONLY = "forward_only"
    BACKWARD_ONLY = "backward_only"
    BIDIRECTIONAL = "bidirectional"


class NodeShape(StrEnum):
    ELLIPSE = "ellipse"
    CIRCLE = "circle"
    DATABASE = "database"
    BOX = "box"
    TEXT = "text"
    DIAMOND = "diamond"
    DOT = "dot"
    STAR = "star"
    TRIANGLE = "triangle"
    TRIANGLE_DOWN = "triangleDown"
    SQUARE = "square"


class Position(StrictModel):
    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


class DefaultView(StrictModel):
    position: Position
    scale: float = Field(strict=True, gt=0, allow_inf_nan=False)


class Room(StrictModel):
    id: MapId
    name: NonEmptyString
    position: Position
    color: str | None = None
    shape: NodeShape = NodeShape.BOX
    notes: str = ""

    @field_validator("id")
    @classmethod
    def reject_reserved_id(cls, value: str) -> str:
        if value == UNKNOWN_ROOM_ID:
            raise ValueError(f"'{UNKNOWN_ROOM_ID}' is reserved for unknown connection endpoints")
        return value


class CharacterGroup(StrictModel):
    id: MapId
    name: NonEmptyString
    location: MapId
    default_position: Position | None = Field(default=None, alias="defaultPosition")
    color: str | None = None
    shape: NodeShape = NodeShape.CIRCLE


class Character(StrictModel):
    name: NonEmptyString
    ancestry: NonEmptyString
    class_name: str = Field(default="", alias="class")
    physical_description: str = ""
    personality: str = ""
    other_details: str = ""
    location: MapId | None = None
    group: MapId | None = None
    default_position: Position | None = Field(default=None, alias="defaultPosition")
    color: str | None = None
    shape: NodeShape = NodeShape.ELLIPSE

    @model_validator(mode="after")
    def validate_placement(self) -> "Character":
        if (self.location is None) == (self.group is None):
            raise ValueError("must have exactly one non-empty 'location' or 'group'")
        return self


class ConnectionStatus(StrictModel):
    id: MapId
    description: NonEmptyString
    display_color: str | None = None
    line_style: Literal["solid", "dashed"] = "solid"


class Connection(StrictModel):
    source: MapId = Field(alias="from")
    target: MapId = Field(alias="to")
    status: MapId
    direction: ConnectionDirection = ConnectionDirection.BIDIRECTIONAL
    name: str = ""
    notes: str = ""


class MapData(StrictModel):
    default_view: DefaultView | None = Field(default=None, alias="defaultView")
    rooms: list[Room] = Field(default_factory=list)
    characters: list[Character] = Field(default_factory=list)
    character_groups: list[CharacterGroup] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    connection_statuses: list[ConnectionStatus] = Field(
        default_factory=list,
        alias="connectionStatus",
    )

    @model_validator(mode="after")
    def validate_references(self) -> "MapData":
        errors: list[str] = []
        room_ids = {room.id for room in self.rooms}
        group_ids = {group.id for group in self.character_groups}
        status_ids = self._unique_ids("connection status", self.connection_statuses, errors)

        self._unique_ids(
            "node",
            [*self.rooms, *self.character_groups],
            errors,
        )
        self._unique_names("character", self.characters, errors)

        for group in self.character_groups:
            if group.location not in room_ids:
                errors.append(
                    f"unknown location '{group.location}' for character group '{group.name}'"
                )

        for character in self.characters:
            if character.location is not None and character.location not in room_ids:
                errors.append(
                    f"unknown location '{character.location}' for character '{character.name}'"
                )
            if character.group is not None and character.group not in group_ids:
                errors.append(f"unknown group '{character.group}' for character '{character.name}'")

        for index, connection in enumerate(self.connections):
            label = connection.name or f"connection #{index + 1}"
            if connection.source not in room_ids and connection.source != UNKNOWN_ROOM_ID:
                errors.append(f"unknown source room '{connection.source}' for {label}")
            if connection.target not in room_ids and connection.target != UNKNOWN_ROOM_ID:
                errors.append(f"unknown target room '{connection.target}' for {label}")
            if connection.status not in status_ids:
                errors.append(f"unknown status '{connection.status}' for {label}")

        if errors:
            raise ValueError("\n".join(dict.fromkeys(errors)))
        return self

    @staticmethod
    def _unique_ids(kind: str, items: list, errors: list[str]) -> set[str]:
        ids: set[str] = set()
        for item in items:
            if item.id in ids:
                errors.append(f"duplicate {kind} id '{item.id}'")
            ids.add(item.id)
        return ids

    @staticmethod
    def _unique_names(kind: str, items: list, errors: list[str]) -> set[str]:
        names: set[str] = set()
        for item in items:
            if item.name in names:
                errors.append(f"duplicate {kind} name '{item.name}'")
            names.add(item.name)
        return names


class InteractionOptions(StrictModel):
    zoom_view: bool = Field(alias="zoomView")
    drag_view: bool = Field(alias="dragView")
    keyboard: bool
    hover: bool
    hide_edges_on_drag: bool = Field(alias="hideEdgesOnDrag")
    hide_nodes_on_drag: bool = Field(alias="hideNodesOnDrag")
    tooltip_delay: int = Field(alias="tooltipDelay", ge=0)


class ScalingOptions(StrictModel):
    min: float
    max: float


class NodeOptions(StrictModel):
    shape: str
    margin: float
    scaling: ScalingOptions


class ArrowEndOptions(StrictModel):
    scale_factor: float = Field(alias="scaleFactor", gt=0)


class ArrowOptions(StrictModel):
    to: ArrowEndOptions
    from_: ArrowEndOptions = Field(alias="from")


class SmoothOptions(StrictModel):
    type: Literal[
        "continuous",
        "discrete",
        "diagonalCross",
        "straightCross",
        "horizontal",
        "vertical",
        "curvedCW",
        "curvedCCW",
        "cubicBezier",
    ]


class EdgeOptions(StrictModel):
    arrows: ArrowOptions
    smooth: SmoothOptions


class GraphOptions(StrictModel):
    interaction: InteractionOptions
    nodes: NodeOptions
    edges: EdgeOptions
