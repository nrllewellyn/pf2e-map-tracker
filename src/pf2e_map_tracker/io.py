"""Load and validate map tracker JSON resources."""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from pf2e_map_tracker.models import GraphOptions, MapData


def load_map_data(path: Path) -> MapData:
    return MapData.model_validate(_load_json(path))


def load_graph_options() -> GraphOptions:
    resource = files("pf2e_map_tracker.resources").joinpath("graphOptions.json")
    return GraphOptions.model_validate(json.loads(resource.read_text(encoding="utf-8")))


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)
