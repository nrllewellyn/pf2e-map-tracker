"""Typed input and graph-option models."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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


class Room(StrictModel):
    name: NonEmptyString
    anchor: bool = False
    color: str | None = None
    shape: NodeShape = NodeShape.BOX
    notes: str = ""


class CharacterGroup(StrictModel):
    name: NonEmptyString
    location: NonEmptyString
    color: str | None = None
    shape: NodeShape = NodeShape.CIRCLE


class Character(StrictModel):
    name: NonEmptyString
    ancestry: NonEmptyString
    class_name: str = Field(default="", alias="class")
    physical_description: str = ""
    personality: str = ""
    other_details: str = ""
    location: NonEmptyString | None = None
    group: NonEmptyString | None = None
    color: str | None = None
    shape: NodeShape = NodeShape.ELLIPSE

    @model_validator(mode="after")
    def validate_placement(self) -> "Character":
        if (self.location is None) == (self.group is None):
            raise ValueError("must have exactly one non-empty 'location' or 'group'")
        return self


class ConnectionStatus(StrictModel):
    name: NonEmptyString
    description: NonEmptyString
    display_color: str | None = None
    line_style: Literal["solid", "dashed"] = "solid"


class Connection(StrictModel):
    source: NonEmptyString = Field(alias="from")
    target: NonEmptyString = Field(alias="to")
    status: NonEmptyString
    direction: ConnectionDirection = ConnectionDirection.BIDIRECTIONAL
    name: str = ""
    notes: str = ""


class MapData(StrictModel):
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
        room_names = self._unique_names("room", self.rooms, errors)
        group_names = self._unique_names("character group", self.character_groups, errors)
        character_names = self._unique_names("character", self.characters, errors)
        status_names = self._unique_names("connection status", self.connection_statuses, errors)

        all_node_names = room_names | group_names | character_names
        if len(all_node_names) != len(room_names) + len(group_names) + len(character_names):
            seen: set[str] = set()
            for node in [*self.rooms, *self.character_groups, *self.characters]:
                if node.name in seen:
                    errors.append(f"duplicate node name '{node.name}'")
                seen.add(node.name)

        for group in self.character_groups:
            if group.location not in room_names:
                errors.append(
                    f"unknown location '{group.location}' for character group '{group.name}'"
                )

        for character in self.characters:
            if character.location is not None and character.location not in room_names:
                errors.append(
                    f"unknown location '{character.location}' for character '{character.name}'"
                )
            if character.group is not None and character.group not in group_names:
                errors.append(f"unknown group '{character.group}' for character '{character.name}'")

        for index, connection in enumerate(self.connections):
            label = connection.name or f"connection #{index + 1}"
            if connection.source not in room_names:
                errors.append(f"unknown source room '{connection.source}' for {label}")
            if connection.target not in room_names:
                errors.append(f"unknown target room '{connection.target}' for {label}")
            if connection.status not in status_names:
                errors.append(f"unknown status '{connection.status}' for {label}")

        if errors:
            raise ValueError("\n".join(dict.fromkeys(errors)))
        return self

    @staticmethod
    def _unique_names(kind: str, items: list, errors: list[str]) -> set[str]:
        names: set[str] = set()
        for item in items:
            if item.name in names:
                errors.append(f"duplicate {kind} name '{item.name}'")
            names.add(item.name)
        return names


class LayoutOptions(StrictModel):
    random_seed: int = Field(alias="randomSeed")


class InteractionOptions(StrictModel):
    zoom_view: bool = Field(alias="zoomView")
    drag_view: bool = Field(alias="dragView")
    keyboard: bool
    hover: bool
    hide_edges_on_drag: bool = Field(alias="hideEdgesOnDrag")
    hide_nodes_on_drag: bool = Field(alias="hideNodesOnDrag")
    tooltip_delay: int = Field(alias="tooltipDelay", ge=0)


class BarnesHutOptions(StrictModel):
    gravitational_constant: float = Field(alias="gravitationalConstant")
    central_gravity: float = Field(alias="centralGravity")
    spring_length: float = Field(alias="springLength")
    spring_constant: float = Field(alias="springConstant")
    damping: float
    avoid_overlap: float = Field(alias="avoidOverlap")


class StabilizationOptions(StrictModel):
    enabled: bool
    iterations: int = Field(gt=0)
    update_interval: int = Field(alias="updateInterval", gt=0)
    only_dynamic_edges: bool = Field(alias="onlyDynamicEdges")


class PhysicsOptions(StrictModel):
    enabled: bool
    barnes_hut: BarnesHutOptions = Field(alias="barnesHut")
    min_velocity: float = Field(alias="minVelocity", ge=0)
    solver: Literal["barnesHut"]
    stabilization: StabilizationOptions


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
    type: str


class EdgeOptions(StrictModel):
    arrows: ArrowOptions
    smooth: SmoothOptions


class GraphOptions(StrictModel):
    layout: LayoutOptions
    interaction: InteractionOptions
    physics: PhysicsOptions
    nodes: NodeOptions
    edges: EdgeOptions
