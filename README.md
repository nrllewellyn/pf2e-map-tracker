# Description

A basic map tracker for a PF2e TTRPG game.

# Updating

- Update `/src/main/resources/roomData.json`
- Run `main.py`
- Updated HTML will be stored in `/docs`

# Room Data JSON Format

NOTE: The file `/src/test/resources/testData.json` is available for testing any code changes.

## `rooms`

| Key     | Type   | Required? | Description / Purpose                                                  | Example value              |
|---------|--------|-----------|------------------------------------------------------------------------|----------------------------|
| `name`  | string | **Yes**   | Unique identifier and displayed label                                  | `"Kitchen"`                |
| `color` | string | No        | Background color of the node (CSS color). Default:  `"#97c2fc"`        | `"#ffcc00"` or `"yellow"`  |
| `notes` | string | No        | Additional text shown in node tooltip on hover. Default: Empty string. | `"Smells funny after 8pm"` |

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
