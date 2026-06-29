"""Command-line interface for map generation and validation."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from pf2e_map_tracker.graph import generate_graph
from pf2e_map_tracker.io import load_graph_options, load_map_data
from pf2e_map_tracker.models import GraphOptions, MapData

DEFAULT_INPUT = Path("data/map_data.json")
DEFAULT_OUTPUT = Path("dist/index.html")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and validate a PF2e map tracker.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Validate data and generate the interactive map.")
    build.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)

    validate = subparsers.add_parser("validate", help="Validate map data and graph options.")
    validate.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    schema = subparsers.add_parser("export-schema", help="Write JSON Schemas for editor tooling.")
    schema.add_argument("--output-dir", type=Path, default=Path("schemas"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            output = generate_graph(args.input, args.output)
            print(f"Graph saved to: {output}")
        elif args.command == "validate":
            load_map_data(args.input)
            load_graph_options()
            print(f"Valid map data: {args.input}")
        else:
            _export_schemas(args.output_dir)
            print(f"Schemas saved to: {args.output_dir}")
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def _export_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "map-data.schema.json": MapData.model_json_schema(by_alias=True),
        "graph-options.schema.json": GraphOptions.model_json_schema(by_alias=True),
    }
    for filename, schema in schemas.items():
        path = output_dir / filename
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
