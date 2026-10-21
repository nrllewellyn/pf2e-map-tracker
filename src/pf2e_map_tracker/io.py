"""Load and validate map tracker JSON resources."""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from pf2e_map_tracker.models import GraphOptions, MapData


def load_map_data(path: Path) -> MapData:
    return MapData.model_validate(parse_json(path.read_text(encoding="utf-8"), path.resolve()))


def load_graph_options() -> GraphOptions:
    resource = files("pf2e_map_tracker.resources").joinpath("graphOptions.json")
    return GraphOptions.model_validate(
        parse_json(resource.read_text(encoding="utf-8"), str(resource))
    )


def parse_json(content: str, source: str | Path) -> Any:
    """Parse JSON, identifying its source and showing context for syntax errors."""
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in {source}: {error.msg} "
            f"(line {error.lineno}, column {error.colno})\n{_json_error_context(error)}"
        ) from error


def _json_error_context(error: json.JSONDecodeError) -> str:
    # Split only on newlines to match JSONDecodeError's line numbering, including
    # an empty final line when parsing stops at the end of a truncated file.
    lines = error.doc.split("\n")
    error_index = error.lineno - 1
    start = max(0, error_index - 2)
    stop = min(len(lines), error_index + 3)
    width = len(str(stop))
    excerpt = []
    for index in range(start, stop):
        line = lines[index].rstrip("\r").expandtabs(4)
        column = len(lines[index][: error.colno - 1].expandtabs(4)) if index == error_index else 0
        # Keep long descriptions and minified JSON readable, with the error in view.
        offset = max(0, column - 60)
        prefix = "..." if offset else ""
        suffix = "..." if len(line) > offset + 120 else ""
        excerpt.append(f"{index + 1:>{width}} | {prefix}{line[offset : offset + 120]}{suffix}")
        if index == error_index:
            excerpt.append(f"{'':>{width}} | {' ' * (column - offset + len(prefix))}^")
    return "\n".join(excerpt)
