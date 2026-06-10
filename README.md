# PF2e Map Tracker

Generate a standalone interactive HTML map for a PF2e campaign. Rooms, connections,
characters, and character groups are defined in JSON and rendered with PyVis.

## Setup

Python 3.11 or newer is required.

```powershell
python -m pip install -e ".[dev]"
```

## Common Commands

Run commands from the repository root:

```powershell
# Validate campaign data and application-owned graph options
pf2e-map-tracker validate

# Generate dist/index.html
pf2e-map-tracker build

# Build from or to a different path
pf2e-map-tracker build --input tests/fixtures/test_data.json --output test-map.html

# Export JSON Schemas for editor integration
pf2e-map-tracker export-schema

# Run automated checks
ruff check .
pytest
```

The same CLI is available through `python -m pf2e_map_tracker`.

## GitHub Pages Deployment

The `Build and deploy map` GitHub Actions workflow validates the project, builds the map, and
publishes the generated `dist` directory whenever changes are pushed to `main`. It can also be
started manually from the repository's **Actions** tab.

Before the first deployment, open the repository's **Settings > Pages** page. Under **Build and
deployment**, change **Source** from **Deploy from a branch** to **GitHub Actions**. This disables
the legacy Jekyll deployment that expects a `/docs` directory and allows the workflow to publish
the generated `dist` artifact directly.

## Project Layout

- `data/room_data.json`: editable campaign map data.
- `dist/index.html`: generated map output; ignored by Git.
- `tests/fixtures/test_data.json`: smaller example map used by automated tests.
- `src/pf2e_map_tracker/models.py`: typed data models and validation.
- `src/pf2e_map_tracker/graph.py`: PyVis graph construction.
- `src/pf2e_map_tracker/resources/graphOptions.json`: layout, physics, and visual options.
- `src/pf2e_map_tracker/resources/graphEnhancements.js`: custom tooltip and visibility UI.
- `schemas/`: generated JSON Schemas for map data and graph options.

`graphOptions.json` is validated before every build. Run `pf2e-map-tracker validate` after
editing it.

## Trusted HTML

Display strings in map data are treated as trusted HTML so notes can contain markup such as
`<b>`, `<br>`, and `<p>`. Only build maps from JSON maintained by trusted authors.

## Map Data Format

All object fields are validated strictly. Unknown fields are rejected so spelling mistakes are
reported instead of silently ignored.

All string fields support emojis and other Unicode characters.

### Rooms

| Field    | Required | Description                                                                                                                                               |
|----------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`   | Yes      | Unique node name and displayed label.                                                                                                                     |
| `anchor` | No       | Invisibly connects anchor rooms for layout stability. Defaults to `false`.                                                                                |
| `color`  | No       | CSS node color.                                                                                                                                           |
| `shape`  | No       | Node shape. Accepts `ellipse`, `circle`, `database`, `box`, `text`, `diamond`, `dot`, `star`, `triangle`, `triangleDown`, or `square`. Defaults to `box`. |
| `notes`  | No       | Trusted HTML shown in the room tooltip.                                                                                                                   |

Two anchors are connected as a pair. Three or more anchors form a ring.

### Characters

| Field                  | Required    | Description                                                                                                                                                   |
|------------------------|-------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`                 | Yes         | Unique node name and displayed label.                                                                                                                         |
| `ancestry`             | Yes         | Ancestry shown in the tooltip.                                                                                                                                |
| `class`                | No          | Class shown in the tooltip.                                                                                                                                   |
| `physical_description` | No          | Trusted HTML shown in the tooltip.                                                                                                                            |
| `personality`          | No          | Trusted HTML shown in the tooltip.                                                                                                                            |
| `other_details`        | No          | Trusted HTML shown in the tooltip.                                                                                                                            |
| `location`             | Conditional | Existing room name. Exactly one of `location` or `group` is required.                                                                                         |
| `group`                | Conditional | Existing character-group name. Exactly one of `location` or `group` is required.                                                                              |
| `color`                | No          | CSS node color.                                                                                                                                               |
| `shape`                | No          | Node shape. Accepts `ellipse`, `circle`, `database`, `box`, `text`, `diamond`, `dot`, `star`, `triangle`, `triangleDown`, or `square`. Defaults to `ellipse`. |

### Character Groups

| Field      | Required | Description                                                                                                                                                  |
|------------|----------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`     | Yes      | Unique node name and displayed label.                                                                                                                        |
| `location` | Yes      | Existing room name.                                                                                                                                          |
| `color`    | No       | CSS node color.                                                                                                                                              |
| `shape`    | No       | Node shape. Accepts `ellipse`, `circle`, `database`, `box`, `text`, `diamond`, `dot`, `star`, `triangle`, `triangleDown`, or `square`.~~~~ Defaults to `circle`. |

### Connections

| Field       | Required | Description                                                                       |
|-------------|----------|-----------------------------------------------------------------------------------|
| `from`      | Yes      | Existing source room name.                                                        |
| `to`        | Yes      | Existing destination room name.                                                   |
| `status`    | Yes      | Existing `connectionStatus` name.                                                 |
| `direction` | No       | `bidirectional`, `forward_only`, or `backward_only`. Defaults to `bidirectional`. |
| `name`      | No       | Connection label shown in the tooltip.                                            |
| `notes`     | No       | Trusted HTML shown in the tooltip.                                                |

### Connection Statuses

| Field           | Required | Description                                   |
|-----------------|----------|-----------------------------------------------|
| `name`          | Yes      | Unique status name referenced by connections. |
| `description`   | Yes      | Human-readable tooltip description.           |
| `display_color` | No       | CSS edge color.                               |
| `line_style`    | No       | `solid` or `dashed`. Defaults to `solid`.     |
