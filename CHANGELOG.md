# Changelog

This changelog will only be updated for software changes, and does not track changes to map data or image files.

## 0.6.0

## Changed
- `language_visual_style` changed to `lettering`

## 0.5.0

### Added

- Embed `<map-sign>` cards between paragraphs in room details, with an NPC Group reference, optional location, description, and translation.
- Preview room sign cards in the editor, including group names, languages, example pictures, and warnings for invalid markup or missing NPC Groups.
- Regression tests for strict description validation, editor preview/save/rebuild persistence, HTML and Unicode rendering, and desktop/mobile gallery layout.

### Changed

- Rename Previous Inhabitants to NPC Groups throughout the viewer, editor, data model, and image directories. Use `npc_groups` in map JSON; the former `previous_occupants` field is
  rejected.
- Rooms, character groups, and connections use `short_description` in place of `notes`; the former field is rejected.
- Show short descriptions without a Notes label in tooltips and before other fields in details panels. Display room names only in the panel heading.
- Use shared sign cards for rooms and connections. Connection sign sides now display as Location with `Entrance from <room name>`, including unknown rooms.
- Move image source paths and alt text into a collapsible Image details section that can be reached with the keyboard.

### Fixed

- Separate short descriptions from the following fields in room, character-group, and connection details panels with a small gap.
- Place the details gallery on the right and let text wrap beside it and continue across the full width below it. Keep sign cards at full width and stack the gallery above text on
  narrow screens.
- Include signs embedded in room details when renaming NPC Group IDs and preventing deletion of referenced NPC groups.
- Load shared detail helpers before the viewer and editor scripts, and serve the shared helpers and styles used by editor previews.

## 0.4.0

### Added

- Add signs on connections
- Additional Information panel with NPC Groups, full group details, rotating example thumbnails, and sign/member picture galleries.
- Editor controls and JSON validation for signs and NPC groups.
- Pick connection endpoints, group locations, and character rooms or groups directly on the editor graph.

### Fixed

- Map editor shortcuts no longer intercept typing or navigation in form fields.
- Picture entries have a remove button beside their source, so adding a picture can be cancelled without discarding a new room.

## 0.3.0

### Added

- Ability to view node/edge images in full screen mode by clicking on them in the details panel.

## 0.2.2

### Fixed

- Automated tests for small screens failing

## 0.2.1

### Added:

- Changelog

### Changed:

- "Character Visibility" now defaults to "Show All"

### Fixed:

- White border box now properly resizes
