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

## Visual Map Editor

Install the optional local editor and launch it from the repository root:

```powershell
python -m pip install -e ".[editor]"
pf2e-map-tracker edit
```

Open the printed URL, normally `http://127.0.0.1:8000`, in your browser. The server
accepts local connections only. Stop it with Ctrl+C. Existing build and validation
commands do not require the editor dependencies.

```powershell
pf2e-map-tracker edit --input tests/fixtures/test_data.json --output dist/test-map.html --port 8123
```

Select a graph node or connection, or search the object list. Use **Add** to create
a room, group, character, connection, or connection status. Fill out the form and
click **Apply**. HTML fields include a rendered preview; formatting is
entered as HTML. Drag rooms to arrange them on a 250 px grid in both directions.
Hold Shift to position freely; Shift can be pressed or released during a drag.
The grid uses map coordinates, so snapping stays consistent at any zoom level.
Numeric coordinate fields allow exact positions without snapping.
Drag groups and characters freely to set their default starting position before
physics settles them. Use **Save** to keep it. Their form shows these coordinates;
click **Use automatic position**, then **Apply**, to clear the default. Use their
placement fields to move them between rooms or groups. Unknown rooms remain
automatically positioned and cannot have a default position.

Pan and zoom to your preferred starting view, then click **Set default view**.
Use **Save** to store it in the map JSON, or **Rebuild graph** to save it and update
the HTML map. Both the editor and generated viewer open at this default.
**Fit graph** changes only the current view; click **Set default view** afterward
to make that view the default. Capturing a view keeps pending object form edits.

Changing a room, group, or status ID updates its references. IDs must use lowercase
letters and digits separated by single hyphens. Referenced objects cannot be
deleted until their dependents are reassigned or removed. Generated unknown-room
nodes select their owning connection; group/character attachment edges select
the attached object. The list always includes objects hidden by the graph's
character visibility control.

**Save** validates and writes the JSON file. **Rebuild graph** saves valid changes
and regenerates the configured HTML output. Both actions apply pending form edits
first; invalid forms block saving. Applied changes stay in memory until saved.
**Reload** discards unsaved changes after confirmation. Closing a dirty editor also
prompts before leaving.

If the JSON file changes outside this editor, saving is blocked to prevent
overwriting it. Copy any unsaved form values you need, then use **Reload** and
reapply your edits. If rebuilding fails after saving, the editor reports
**Changes saved; rebuild failed** and retains the previous HTML; fix the reported
problem and retry **Rebuild graph**. Invalid or unreadable input is reported without
overwriting it; correct the file externally and click **Reload**.

The editor serves its graph library locally and does not publish, commit, or push
changes. The generated viewer and GitHub Pages deployment retain their existing
behavior. This version is intended for one local author and has no undo history.

To run the editor API tests and browser workflow tests:

```powershell
python -m pip install -e ".[dev,editor]"
python -m playwright install chromium
pytest
pytest tests/test_editor_browser.py --run-editor-browser
```

## GitHub Pages Deployment

The `Build and deploy map` GitHub Actions workflow validates the project, builds the map, and
publishes the generated `dist` directory whenever changes are pushed to `main`. It can also be
started manually from the repository's **Actions** tab.

Before the first deployment, open the repository's **Settings > Pages** page. Under **Build and
deployment**, change **Source** from **Deploy from a branch** to **GitHub Actions**. This disables
the legacy Jekyll deployment that expects a `/docs` directory and allows the workflow to publish
the generated `dist` artifact directly.

## Project Layout

- `data/map_data.json`: editable campaign map data.
- `dist/index.html`: generated map output; ignored by Git.
- `tests/fixtures/test_data.json`: smaller example map used by automated tests.
- `src/pf2e_map_tracker/models.py`: typed data models and validation.
- `src/pf2e_map_tracker/graph.py`: PyVis graph construction.
- `src/pf2e_map_tracker/resources/graphOptions.json`: interaction and visual options.
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

Display text fields support emojis and other Unicode characters. For symbols that support both text and emoji presentation, such as `🛡` and `🛡️`, use the
emoji-presentation variant (U+FE0F) in node names to reliably render the colorful emoji.

Rooms, character groups, and connection statuses require an `id` containing lowercase letters and
digits separated by single hyphens (lower-kabob-case). Room and character-group IDs share a unique namespace.
Connection-status IDs are unique separately. Character names must be unique because characters do
not have IDs; ID-backed object names do not need to be unique.

### Default view

The optional top-level `defaultView` field sets the initial map center and zoom:

```json
"defaultView": {
  "position": {"x": -1200, "y": 500},
  "scale": 0.75
}
```

Coordinates use the same map space as room positions. `scale` must be a finite,
positive number: `1` means 100% zoom, `0.5` means 50%, and `2` means 200%.
Both coordinates must be finite numbers. Omit `defaultView` or set it to `null`
to fit the whole graph on opening. Panning and zooming do not change the saved
default unless you capture the view again.

### Rooms

| Field    | Required | Description                                                                                                                                               |
|----------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`     | Yes      | Globally unique node ID used by references.                                                                                                               |
| `name`   | Yes      | Displayed label.                                                                                                                                          |
| `position` | Yes    | Saved coordinates, for example `{"x": -1200, "y": 0}`. Both coordinates must be finite numbers.                                                            |
| `color`  | No       | CSS node color.                                                                                                                                           |
| `shape`  | No       | Node shape. Accepts `ellipse`, `circle`, `database`, `box`, `text`, `diamond`, `dot`, `star`, `triangle`, `triangleDown`, or `square`. Defaults to `box`. |
| `notes`  | No       | Trusted HTML shown in the room tooltip.                                                                                                                   |

The room ID `unknown` is reserved and must not appear in `rooms`.

#### Room positions and automatic placement

Rooms stay at their saved `position` coordinates. The campaign map uses a compact arrangement
that separates connection paths; the test fixture uses a grid. Edit `x` and `y` to arrange rooms
differently. Positive
`x` moves right and positive `y` moves down. Zero, negative, and fractional coordinates are valid.
Room connections do not determine positions or impose a hierarchy: cycles, disconnected rooms,
parallel connections, and all supported arrow directions remain valid.

Character groups and characters may have an optional `defaultPosition`, with finite `x` and `y`
coordinates, used only as the starting position before physics. Without it, character groups
and direct characters start near their room, and group members start near their group
(including a group's default position). Each Unknown Room node starts near its connected room; unknown-to-unknown pairs start
beyond the room grid. These nodes settle using internal physics settings while rooms remain
fixed. Rebuilding after changing a room coordinate or a placement reference updates nearby-node
starting positions. Automatically settled coordinates are not saved back to JSON.

Node dragging is disabled in the generated viewer. Panning, zooming, selection, tooltips, and character visibility remain
available. Visibility changes do not move rooms. Physics and automatic layout settings are not
editable in `graphOptions.json`; edge smoothing supports only static curve types.

Older maps must add a `position` to every room and remove `anchor` fields before validation or
building succeeds. Missing room coordinates are errors; builds do not generate fallback positions.
Groups and characters use `defaultPosition` instead of `position` fields. Legacy `layout` and `physics` blocks must
also be removed from graph options.

### Characters

| Field                  | Required    | Description                                                                                                                                                   |
|------------------------|-------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`                 | Yes         | Unique character name and displayed label.                                                                                                                     |
| `ancestry`             | Yes         | Ancestry shown in the tooltip.                                                                                                                                |
| `class`                | No          | Class shown in the tooltip.                                                                                                                                   |
| `physical_description` | No          | Trusted HTML shown in the tooltip.                                                                                                                            |
| `personality`          | No          | Trusted HTML shown in the tooltip.                                                                                                                            |
| `other_details`        | No          | Trusted HTML shown in the tooltip.                                                                                                                            |
| `location`             | Conditional | Existing room ID. Exactly one of `location` or `group` is required.                                                                                           |
| `group`                | Conditional | Existing character-group ID. Exactly one of `location` or `group` is required.                                                                                |
| `defaultPosition`      | No          | Starting coordinates before physics, for example `{"x": -1200, "y": 0}`. Omit or use `null` for automatic placement. |
| `color`                | No          | CSS node color.                                                                                                                                               |
| `shape`                | No          | Node shape. Accepts `ellipse`, `circle`, `database`, `box`, `text`, `diamond`, `dot`, `star`, `triangle`, `triangleDown`, or `square`. Defaults to `ellipse`. |

### Character Groups

| Field      | Required | Description                                                                                                                                                  |
|------------|----------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`       | Yes      | Globally unique node ID used by references.                                                                                                                  |
| `name`     | Yes      | Displayed label.                                                                                                                                             |
| `location` | Yes      | Existing room ID.                                                                                                                                            |
| `defaultPosition` | No | Starting coordinates before physics, for example `{"x": -1200, "y": 0}`. Omit or use `null` for automatic placement. |
| `color`    | No       | CSS node color.                                                                                                                                              |
| `shape`    | No       | Node shape. Accepts `ellipse`, `circle`, `database`, `box`, `text`, `diamond`, `dot`, `star`, `triangle`, `triangleDown`, or `square`. Defaults to `circle`. |

### Connections

| Field       | Required | Description                                                                       |
|-------------|----------|-----------------------------------------------------------------------------------|
| `from`      | Yes      | Existing source room ID.                                                          |
| `to`        | Yes      | Existing destination room ID.                                                     |
| `status`    | Yes      | Existing `connectionStatus` ID.                                                   |
| `direction` | No       | `bidirectional`, `forward_only`, or `backward_only`. Defaults to `bidirectional`. |
| `name`      | No       | Connection label shown in the tooltip.                                            |
| `notes`     | No       | Trusted HTML shown in the tooltip.                                                |

Connections may use the reserved room ID `unknown` in `from` or `to`. Each reference creates a
separate virtual node named **Unknown room** on the graph.

### Connection Statuses

| Field           | Required | Description                                   |
|-----------------|----------|-----------------------------------------------|
| `id`            | Yes      | Unique status ID referenced by connections.   |
| `description`   | Yes      | Human-readable tooltip description.           |
| `display_color` | No       | CSS edge color.                               |
| `line_style`    | No       | `solid` or `dashed`. Defaults to `solid`.     |
