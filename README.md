# Description

A basic map tracker for a PF2e TTRPG game.

# Updating

- Update `/src/main/resources/roomData.json`
- Run `main.py`
- Updated HTML will be stored in `/docs`

# Room Data JSON Format

NOTE: The file `/src/main/resources/testData.json` is available for testing any code changes.

## `rooms`

| Key     | Type   | Required? | Description / Purpose                                                  | Example value              |
|---------|--------|-----------|------------------------------------------------------------------------|----------------------------|
| `name`  | string | **Yes**   | Unique identifier and displayed label                                  | `"Kitchen"`                |
| `color` | string | No        | Background color of the node (CSS color). Default:  `"#97c2fc"`        | `"#ffcc00"` or `"yellow"`  |
| `notes` | string | No        | Additional text shown in node tooltip on hover. Default: Empty string. | `"Smells funny after 8pm"` |

## `characters`

| Key           | Type   | Required? | Description / Purpose                                                        | Example value                    |
|---------------|--------|-----------|------------------------------------------------------------------------------|----------------------------------|
| `name`        | string | **Yes**   | Unique identifier and displayed label. Must not match another node name.     | `"Valeros"`                      |
| `ancestry`    | string | **Yes**   | Character ancestry shown in the node tooltip.                                | `"Human"`                        |
| `class`       | string | No        | Character class shown in the node tooltip. Default: Empty string.             | `"Fighter"`                      |
| `physical_description` | string | No | Physical description shown in the node tooltip. Default: Empty string.       | `"Tall and heavily armored."`    |
| `personality` | string | No        | Personality description shown in the node tooltip. Default: Empty string.    | `"Quietly confident."`           |
| `other_details` | string | No      | Any other character details shown in the node tooltip. Default: Empty string.| `"Travels with the armorer."`    |
| `location`    | string | Conditional | Current location. Must match a room `name`. Exactly one of `location` or `group` is required. | `"Entrance"` |
| `group`       | string | Conditional | Current character group. Must match a `character_groups` name. Exactly one of `location` or `group` is required. | `"Pathfinders"` |
| `color`       | string | No        | Background color of the character node (CSS color). Uses the default if absent. | `"#ffcc00"` or `"yellow"`     |

Characters are displayed as ellipse-shaped nodes. Each character is automatically connected to either its location or its group by a dashed, neutral-colored line.

## `character_groups`

| Key        | Type   | Required? | Description / Purpose                                                        | Example value       |
|------------|--------|-----------|------------------------------------------------------------------------------|---------------------|
| `name`     | string | **Yes**   | Unique identifier and displayed label. Must not match another node name.     | `"Pathfinders"`     |
| `location` | string | **Yes**   | Current location. Must match a room `name`.                                  | `"Entrance"`        |
| `color`    | string | No        | Background color of the group node (CSS color). Uses the default if absent.  | `"#ffcc00"`         |

Character groups are displayed as circle-shaped nodes with their location and member names in the tooltip. Each group is automatically connected to its location by a dashed, neutral-colored line.

## `connections`

| Key         | Type   | Required? | Description / Purpose                                                                                                             | Example value            |
|-------------|--------|-----------|-----------------------------------------------------------------------------------------------------------------------------------|--------------------------|
| `from`      | string | **Yes**   | Name of the source room (must match a room `name`)                                                                                | `"Hallway"`              |
| `to`        | string | **Yes**   | Name of the destination room                                                                                                      | `"Armory"`               |
| `status`    | string | **Yes**   | References a status name from `connectionStatus`                                                                                  | `"locked"`               |
| `direction` | string | No        | Connection description. If present, must be `"bidirectional"`, `"forward_only"`, or `"backward_only"`. Default: `"bidirectional"` | `"bidirectional"`        |
| `name`      | string | No        | Optional short label/name for this specific connection. Default: Empty string.                                                    | `"Heavy iron door"`      |
| `notes`     | string | No        | Extra info shown in edge tooltip. Defailt: Empty string.                                                                          | `"Requires red keycard"` |

## `connectionStatus`

| Key             | Type   | Required? | Description / Purpose                                      | Example value                    |
|-----------------|--------|-----------|------------------------------------------------------------|----------------------------------|
| `name`          | string | **Yes**   | Unique identifier — referenced in connections              | `"locked"`                       |
| `description`   | string | **Yes**   | Human-readable explanation (shown in edge tooltip)         | `"Requires key or code to pass"` |
| `display_color` | string | No        | Color of the edge/arrow (CSS color). Default: `"#aaaaaa"`  | `"#ff4444"` or `"red"`           |
| `line_style`    | string | No        | Must be either `"solid"` or `"dashed"`. Default: `"solid"` | `solid`                          |                          
