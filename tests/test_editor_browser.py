"""Real Chromium workflows; opt in with --run-editor-browser."""

import json
import socket
import threading
import time

import pytest


@pytest.fixture(scope="module")
def browser(request):
    if not request.config.getoption("--run-editor-browser"):
        pytest.skip("Use --run-editor-browser to run Chromium workflows")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def editor_server(tmp_path, browser):
    import uvicorn

    from pf2e_map_tracker.editor import create_app

    data = {
        "rooms": [
            {"id": "hall", "name": "Hall", "position": {"x": -400, "y": 0}},
            {"id": "study", "name": "Study", "position": {"x": 400, "y": 0}},
        ],
        "character_groups": [{"id": "party", "name": "Party", "location": "hall"}],
        "characters": [{"name": "Hero", "ancestry": "Human", "group": "party"}],
        "connectionStatus": [{"id": "open", "description": "Open"}],
        "connections": [
            {"from": "hall", "to": "study", "status": "open"},
            {"from": "hall", "to": "study", "status": "open", "name": "Second route"},
        ],
    }
    source = tmp_path / "map.json"
    source.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    output = tmp_path / "map.html"
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(source, output), log_level="error", timeout_graceful_shutdown=2)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            pytest.fail("Editor test server did not start")
        time.sleep(0.01)
    try:
        yield {"url": f"http://127.0.0.1:{port}", "source": source, "output": output}
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "Editor server did not stop"


@pytest.fixture
def page(browser, editor_server):
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(editor_server["url"])
    page.wait_for_function("window.mapEditor?.network && !window.mapEditor.busy")
    yield page
    page.close()
    assert not errors, errors


def wait_idle(page):
    page.wait_for_function("!window.mapEditor.busy")


def choose(page, kind, index=0):
    page.locator(f'.object-item[data-kind="{kind}"][data-index="{index}"]').click()


def apply(page):
    page.get_by_role("button", name="Apply", exact=True).click()
    wait_idle(page)


def add(page, kind):
    page.locator("#add-kind").select_option(kind)
    page.get_by_role("button", name="Add", exact=True).click()


def graph_point(page, node_id):
    page.locator("#graph").scroll_into_view_if_needed()
    canvas = page.locator("#graph").bounding_box()
    point = page.evaluate(
        "id => mapEditor.network.canvasToDOM(mapEditor.network.getPositions([id])[id])",
        node_id,
    )
    return canvas["x"] + point["x"], canvas["y"] + point["y"]


@pytest.mark.parametrize("kind", ["rooms", "character_groups", "connections"])
def test_short_description_preview_and_save(page, editor_server, kind):
    description = "<em>Brief description 🧭</em>\nSecond line"
    choose(page, kind)
    assert page.locator("#field-notes").count() == 0
    page.locator("#field-short_description").fill(description)
    preview = page.frame_locator('iframe[title="Short description (HTML) preview"]')
    assert preview.locator("em").inner_text() == "Brief description 🧭"
    apply(page)
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)

    record = json.loads(editor_server["source"].read_bytes())[kind][0]
    assert record["short_description"] == description
    assert "notes" not in record
    page.get_by_role("button", name="Reload", exact=True).click()
    wait_idle(page)
    choose(page, kind)
    assert page.locator("#field-short_description").input_value() == description


@pytest.mark.parametrize("new_connection", [False, True])
@pytest.mark.parametrize("width", [390, 1500])
def test_pick_connection_rooms_on_graph(page, editor_server, new_connection, width):
    page.set_viewport_size({"width": width, "height": 1000})
    original = editor_server["source"].read_bytes()
    if new_connection:
        add(page, "connections")
    else:
        choose(page, "connections")
    page.locator("#field-name").fill("Graph route")
    page.locator("#field-short_description").fill("<p>Keep these notes.</p>")
    page.locator("#field-status").select_option("open")
    page.locator("#field-direction").select_option("forward_only")
    page.evaluate("mapEditor.network.moveTo({position: {x: 0, y: 0}, scale: 0.3})")
    selection = page.evaluate("mapEditor.selection")
    for field, room in [("from", "study"), ("to", "hall")]:
        pick = page.locator(f"#pick-{field}")
        pick.click()
        assert pick.get_attribute("aria-pressed") == "true"
        assert page.locator("#room-pick-banner").is_visible()
        assert page.evaluate("mapEditor.network.interactionHandler.options.dragNodes") is False
        page.screenshot(path=str(editor_server["source"].parent / f"pick-{field}.png"))
        page.mouse.click(*graph_point(page, room))
        assert page.locator(f"#field-{field}").input_value() == room
        assert not page.locator("#room-pick-banner").is_visible()
        assert pick.get_attribute("aria-pressed") == "false"
        assert page.evaluate("mapEditor.selection") == selection
        assert page.locator("#field-name").input_value() == "Graph route"
        assert page.locator("#field-short_description").input_value() == "<p>Keep these notes.</p>"
        assert page.evaluate("mapEditor.network.interactionHandler.options.dragNodes") is True
    assert page.evaluate("mapEditor.network.getScale()") == pytest.approx(0.3)
    assert page.evaluate("mapEditor.network.getViewPosition()") == pytest.approx({"x": 0, "y": 0})
    assert editor_server["source"].read_bytes() == original
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    saved = json.loads(editor_server["source"].read_bytes())["connections"]
    connection = saved[-1] if new_connection else saved[0]
    assert connection["from"] == "study"
    assert connection["to"] == "hall"
    assert connection["name"] == "Graph route"
    assert connection["short_description"] == "<p>Keep these notes.</p>"
    assert connection["direction"] == "forward_only"
    assert len(saved) == (3 if new_connection else 2)


@pytest.mark.parametrize("new_object", [False, True])
@pytest.mark.parametrize("width", [390, 1500])
@pytest.mark.parametrize(
    "kind,field,target",
    [
        ("character_groups", "location", "study"),
        ("characters", "location", "study"),
        ("characters", "group", "party"),
    ],
)
def test_pick_group_and_character_placement(
    page, editor_server, kind, field, target, new_object, width
):
    page.set_viewport_size({"width": width, "height": 1000})
    original = editor_server["source"].read_bytes()
    if new_object:
        add(page, kind)
    else:
        choose(page, kind)
    name = "Pending group" if kind == "character_groups" else "Pending hero"
    details = "short_description" if kind == "character_groups" else "physical_description"
    page.locator("#field-name").fill(name)
    page.locator(f"#field-{details}").fill("<p>Keep these details.</p>")
    page.locator("#field-x").fill("-123.5")
    page.locator("#field-y").fill("250")
    if kind == "characters":
        page.locator("#field-ancestry").fill("Human")
        page.locator("#placement-mode").select_option(field)
    page.wait_for_function("mapEditor.network.physics.stabilized")
    page.evaluate("mapEditor.network.moveTo({position: {x: 0, y: 0}, scale: 0.3})")
    selection = page.evaluate("mapEditor.selection")
    draft = page.evaluate("JSON.stringify(mapEditor.data)")
    pick = page.locator(f"#pick-{field}")
    pick.click()
    assert pick.get_attribute("aria-pressed") == "true"
    assert page.locator("#room-pick-banner").is_visible()
    assert page.evaluate("mapEditor.network.interactionHandler.options.dragNodes") is False
    page.screenshot(path=str(editor_server["source"].parent / "pick-placement.png"))
    page.mouse.click(*graph_point(page, target))
    assert page.locator(f"#field-{field}").input_value() == target
    assert not page.locator("#room-pick-banner").is_visible()
    assert pick.get_attribute("aria-pressed") == "false"
    assert page.evaluate("mapEditor.network.interactionHandler.options.dragNodes") is True
    assert page.evaluate("mapEditor.selection") == selection
    assert page.evaluate("JSON.stringify(mapEditor.data)") == draft
    assert page.evaluate("mapEditor.formDirty") is True
    assert page.locator("#field-name").input_value() == name
    assert page.locator(f"#field-{details}").input_value() == "<p>Keep these details.</p>"
    assert page.locator("#field-x").input_value() == "-123.5"
    assert page.locator("#field-y").input_value() == "250"
    assert editor_server["source"].read_bytes() == original
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    saved = json.loads(editor_server["source"].read_bytes())[kind]
    item = saved[-1] if new_object else saved[0]
    assert item[field] == target
    assert item["name"] == name
    assert item[details] == "<p>Keep these details.</p>"
    assert item["defaultPosition"] == {"x": -123.5, "y": 250}
    if kind == "characters":
        assert ("group" if field == "location" else "location") not in item


@pytest.mark.parametrize(
    "kind,field,target,wrong_target",
    [
        ("character_groups", "location", "study", "party"),
        ("characters", "location", "study", "party"),
        ("characters", "group", "party", "hall"),
    ],
)
def test_placement_picking_rejects_other_objects_and_unknown_rooms(
    page, kind, field, target, wrong_target
):
    choose(page, "connections")
    page.locator("#field-to").select_option("unknown")
    apply(page)
    choose(page, kind)
    if kind == "characters":
        page.locator("#placement-mode").select_option(field)
    control = page.locator(f"#field-{field}")
    original = control.input_value()
    selection = page.evaluate("mapEditor.selection")
    page.locator(f"#pick-{field}").click()
    for click in [
        {"nodes": [wrong_target], "edges": []},
        {"nodes": ["__character-0"], "edges": []},
        {"nodes": ["__unknown-0-target"], "edges": []},
        {"nodes": [], "edges": ["editor-edge-0"]},
        {"nodes": [], "edges": []},
    ]:
        page.evaluate("click => mapEditor.network.emit('click', click)", click)
        assert page.locator("#room-pick-banner").is_visible()
        assert control.input_value() == original
        assert page.evaluate("mapEditor.selection") == selection
    page.evaluate("id => mapEditor.network.emit('click', {nodes: [id], edges: []})", target)
    assert control.input_value() == target
    assert not page.locator("#room-pick-banner").is_visible()


@pytest.mark.parametrize("method", ["button", "escape", "toggle", "dropdown"])
def test_cancel_group_picking_keeps_character_form(page, method):
    choose(page, "characters")
    page.locator("#field-name").fill("Pending hero")
    page.locator("#pick-group").click()
    if method == "button":
        page.get_by_role("button", name="Cancel picking", exact=True).click()
    elif method == "escape":
        page.keyboard.press("Escape")
    elif method == "toggle":
        page.locator("#pick-group").click()
    else:
        page.locator("#field-group").select_option("")
    assert not page.locator("#room-pick-banner").is_visible()
    assert page.locator("#pick-group").get_attribute("aria-pressed") == "false"
    assert page.locator("#field-group").input_value() == ("" if method == "dropdown" else "party")
    assert page.locator("#field-name").input_value() == "Pending hero"
    assert page.evaluate("mapEditor.selection") == {"kind": "characters", "index": 0}
    assert page.evaluate("mapEditor.network.interactionHandler.options.dragNodes") is True


@pytest.mark.parametrize("mode", ["location", "group"])
def test_changing_character_placement_mode_exits_picking(page, mode):
    choose(page, "characters")
    page.locator("#field-name").fill("Pending hero")
    page.locator("#placement-mode").select_option(mode)
    page.locator(f"#pick-{mode}").click()
    next_mode = "location" if mode == "group" else "group"
    page.locator("#placement-mode").select_option(next_mode)
    assert not page.locator("#room-pick-banner").is_visible()
    assert page.evaluate("mapEditor.network.interactionHandler.options.dragNodes") is True
    assert page.locator(f"#pick-{next_mode}").get_attribute("aria-pressed") == "false"
    page.locator(f"#pick-{next_mode}").click()
    target = "study" if next_mode == "location" else "party"
    page.evaluate("id => mapEditor.network.emit('click', {nodes: [id], edges: []})", target)
    assert page.locator(f"#field-{next_mode}").input_value() == target
    assert not page.locator("#room-pick-banner").is_visible()
    assert page.locator("#field-name").input_value() == "Pending hero"


@pytest.mark.parametrize("method", ["button", "escape", "toggle", "dropdown"])
def test_cancel_room_picking_keeps_connection_form(page, editor_server, method):
    original = editor_server["source"].read_bytes()
    add(page, "connections")
    page.locator("#field-name").fill("Pending route")
    page.locator("#field-from").select_option("hall")
    page.locator("#pick-from").click()
    # Only the most recently requested endpoint should accept a graph click.
    page.locator("#pick-to").click()
    assert page.locator("#pick-from").get_attribute("aria-pressed") == "false"
    assert page.locator("#pick-to").get_attribute("aria-pressed") == "true"
    if method == "button":
        page.get_by_role("button", name="Cancel picking", exact=True).click()
    elif method == "escape":
        page.keyboard.press("Escape")
    elif method == "toggle":
        page.locator("#pick-to").click()
    else:
        page.locator("#field-to").select_option("study")
    assert not page.locator("#room-pick-banner").is_visible()
    assert page.locator("#field-from").input_value() == "hall"
    assert page.locator("#field-to").input_value() == ("study" if method == "dropdown" else "")
    assert page.locator("#field-name").input_value() == "Pending route"
    assert page.evaluate("mapEditor.selection") == {"kind": "connections", "index": None}
    assert page.evaluate("mapEditor.network.interactionHandler.options.dragNodes") is True
    assert editor_server["source"].read_bytes() == original


def test_room_picking_ignores_other_objects_and_allows_panning(page):
    add(page, "connections")
    page.locator("#field-name").fill("Pending route")
    page.evaluate("mapEditor.network.moveTo({position: {x: 0, y: 0}, scale: 0.3})")
    before = page.evaluate("JSON.stringify(mapEditor.data)")
    page.locator("#pick-to").click()
    for target in [
        {"nodes": ["party"], "edges": []},
        {"nodes": ["__character-0"], "edges": []},
        {"nodes": [], "edges": ["editor-edge-0"]},
        {"nodes": [], "edges": []},
    ]:
        page.evaluate("target => mapEditor.network.emit('click', target)", target)
        assert page.locator("#room-pick-banner").is_visible()
        assert page.locator("#field-to").input_value() == ""
        assert page.locator("#field-name").input_value() == "Pending route"
    x, y = graph_point(page, "hall")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 60, y + 50, steps=10)
    page.mouse.up()
    assert page.evaluate("JSON.stringify(mapEditor.data)") == before
    assert page.locator("#room-pick-banner").is_visible()
    assert page.evaluate("mapEditor.network.getViewPosition().x") != 0
    page.mouse.click(*graph_point(page, "study"))
    assert page.locator("#field-to").input_value() == "study"
    assert page.locator("#field-name").input_value() == "Pending route"


def test_pick_unknown_room_keeps_source_ids(page, editor_server):
    choose(page, "connections")
    page.locator("#field-to").select_option("unknown")
    apply(page)
    add(page, "connections")
    page.locator("#field-status").select_option("open")
    page.locator("#field-to").select_option("hall")
    page.locator("#pick-from").click()
    page.evaluate("mapEditor.network.emit('click', {nodes: ['__unknown-0-target'], edges: []})")
    assert page.locator("#field-from").input_value() == "unknown"
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    saved = json.loads(editor_server["source"].read_bytes())["connections"][-1]
    assert saved["from"] == "unknown"
    assert saved["to"] == "hall"


@pytest.mark.parametrize(
    "kind,field", [("connections", "to"), ("character_groups", "location"), ("characters", "group")]
)
def test_leaving_form_exits_map_picking(page, kind, field):
    choose(page, kind)
    page.locator(f"#pick-{field}").click()
    choose(page, "rooms")
    assert not page.locator("#room-pick-banner").is_visible()
    assert page.evaluate("mapEditor.network.interactionHandler.options.dragNodes") is True
    page.mouse.click(*graph_point(page, "study"))
    assert page.locator("#field-id").input_value() == "study"


def test_editor_dropdowns_alphabetize_display_labels_without_reordering_data(page, editor_server):
    source = editor_server["source"]
    data = json.loads(source.read_bytes())
    data["rooms"][0]["name"] = "zebra Hall"
    data["rooms"][1]["name"] = "Alpha Study"
    data["rooms"].append({"id": "a-annex", "name": "beta Annex", "position": {"x": 0, "y": 400}})
    data["character_groups"][0]["name"] = "zebra Party"
    data["character_groups"].extend(
        [
            {"id": "z-scouts", "name": "Alpha scouts", "location": "hall"},
            {"id": "a-watch", "name": "beta watch", "location": "study"},
        ]
    )
    data["connectionStatus"][0]["description"] = "zebra Open"
    data["connectionStatus"].extend(
        [
            {"id": "z-closed", "description": "Alpha closed"},
            {"id": "a-hidden", "description": "beta hidden"},
        ]
    )
    data["npc_groups"] = [
        {"id": "a-scribes", "name": "zebra Scribes"},
        {"id": "z-wardens", "name": "Alpha Wardens"},
        {"id": "m-builders", "name": "beta Builders"},
    ]
    source.write_text(json.dumps(data), encoding="utf-8")
    original = source.read_bytes()
    page.get_by_role("button", name="Reload", exact=True).click()
    wait_idle(page)

    def values(selector):
        return page.locator(selector).evaluate(
            "control => [...control.options].filter(option => option.value)"
            ".map(option => option.value)"
        )

    def assert_sorted_dropdowns():
        for control in page.locator("select").all():
            options = control.evaluate(
                "control => [...control.options]"
                ".map(option => ({value: option.value, text: option.text}))"
            )
            texts = [option["text"] for option in options if option["value"]]
            assert texts == sorted(texts, key=str.casefold)
            if any(not option["value"] for option in options):
                assert options[0]["value"] == ""

    assert page.locator("#add-kind").input_value() == "rooms"
    assert page.locator("#visibility").input_value() == "show_all"
    choose(page, "rooms")
    assert_sorted_dropdowns()
    choose(page, "character_groups")
    assert values("#field-location") == ["study", "a-annex", "hall"]
    assert page.locator("#field-location").input_value() == "hall"
    assert_sorted_dropdowns()
    choose(page, "characters")
    assert values("#field-group") == ["z-scouts", "a-watch", "party"]
    assert page.locator("#field-group").input_value() == "party"
    assert page.locator("#placement-mode").input_value() == "group"
    assert_sorted_dropdowns()
    page.locator("#placement-mode").select_option("location")
    assert values("#field-location") == ["study", "a-annex", "hall"]
    assert_sorted_dropdowns()
    page.once("dialog", lambda dialog: dialog.accept())
    choose(page, "connectionStatus")
    assert_sorted_dropdowns()
    choose(page, "connections")
    for field in ["from", "to"]:
        assert values(f"#field-{field}") == ["study", "a-annex", "unknown", "hall"]
    assert values("#field-status") == ["z-closed", "a-hidden", "open"]
    assert page.locator("#field-from").input_value() == "hall"
    assert page.locator("#field-to").input_value() == "study"
    assert page.locator("#field-status").input_value() == "open"
    page.get_by_role("button", name="Add sign", exact=True).click()
    assert values("#sign-0-group") == ["z-wardens", "m-builders", "a-scribes"]
    assert_sorted_dropdowns()
    assert page.evaluate("mapEditor.data") == data
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "selector,text",
    [
        ("#search", "hall-west + east = [rooms]"),
        ("#field-id", "hall-west"),
        ("#field-name", "Hall - Study + Library"),
        ("#field-short_description", "<p>North-south + east-west = [routes]</p>"),
        ("#field-x", "-123.5"),
        ("#image-0-caption", "Map - level + room = [1]"),
    ],
)
def test_graph_hotkeys_do_not_intercept_text_fields(page, selector, text):
    choose(page, "rooms")
    page.get_by_role("button", name="Add picture", exact=True).click()
    control = page.locator(selector)
    control.fill("")
    view = page.evaluate("mapEditor.network.getViewPosition()")
    scale = page.evaluate("mapEditor.network.getScale()")
    # Moving over the graph must not steal focus from the field being edited.
    page.locator("#graph canvas").hover()
    page.keyboard.type(text, delay=10)
    page.keyboard.press("ArrowLeft", delay=50)
    page.keyboard.press("ArrowRight", delay=50)
    assert control.input_value() == text
    assert control.evaluate("input => input === document.activeElement")
    assert page.evaluate("mapEditor.network.getScale()") == pytest.approx(scale)
    assert page.evaluate("mapEditor.network.getViewPosition()") == pytest.approx(view)


def test_graph_hotkeys_work_when_canvas_has_focus(page):
    choose(page, "rooms")
    canvas = page.locator("#graph canvas")
    canvas.click(position={"x": 10, "y": 10})
    scale = page.evaluate("mapEditor.network.getScale()")
    page.keyboard.down("-")
    try:
        page.wait_for_function("scale => mapEditor.network.getScale() < scale", arg=scale)
    finally:
        page.keyboard.up("-")
    scale = page.evaluate("mapEditor.network.getScale()")
    page.keyboard.down("=")
    try:
        page.wait_for_function("scale => mapEditor.network.getScale() > scale", arg=scale)
    finally:
        page.keyboard.up("=")
    view = page.evaluate("mapEditor.network.getViewPosition()")
    page.keyboard.down("ArrowRight")
    try:
        page.wait_for_function("view => mapEditor.network.getViewPosition().x > view.x", arg=view)
        # Releasing a held shortcut in a field must not leave the map moving.
        page.locator("#field-name").focus()
    finally:
        page.keyboard.up("ArrowRight")
    view = page.evaluate("mapEditor.network.getViewPosition()")
    scale = page.evaluate("mapEditor.network.getScale()")
    page.keyboard.type("-+", delay=50)
    page.evaluate("""() => new Promise(resolve =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)))""")
    assert page.locator("#field-name").input_value() == "Hall-+"
    assert page.evaluate("mapEditor.network.getScale()") == pytest.approx(scale)
    assert page.evaluate("mapEditor.network.getViewPosition()") == pytest.approx(view)


def test_graph_hotkeys_do_not_intercept_select_controls(page):
    choose(page, "rooms")
    control = page.locator("#field-shape")
    control.select_option("box")
    control.focus()
    view = page.evaluate("mapEditor.network.getViewPosition()")
    scale = page.evaluate("mapEditor.network.getScale()")
    control.press("ArrowDown", delay=50)
    assert control.input_value() != "box"
    assert page.evaluate("mapEditor.network.getScale()") == pytest.approx(scale)
    assert page.evaluate("mapEditor.network.getViewPosition()") == pytest.approx(view)


def test_edit_npc_groups_signs_rename_protection_and_image_collections(page, editor_server):
    picture = editor_server["source"].parent / "example.svg"
    picture.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        '<rect width="200" height="100" fill="blue"/></svg>',
        encoding="utf-8",
    )
    add(page, "npc_groups")
    assert page.locator('#add-kind option[value="npc_groups"]').inner_text() == "NPC group"
    assert page.locator("#form-title").inner_text() == "New NPC group"
    page.locator("#field-name").fill("Old Wardens")
    page.locator("#field-language").fill("Dwarven")
    page.get_by_label("Lettering (HTML)", exact=True).fill("Angular runes")
    page.get_by_label("Language oddities (HTML)", exact=True).fill("<b>Runes feel warm</b>")
    page.locator("#field-signage_physical_form").fill("Stone plaques")
    page.locator("#field-communication_quirks").fill("Warnings first")
    page.locator("#field-known_ancestries").fill("Dwarf\nHuman")
    page.locator("#field-common_appearance").fill("Brass badges")
    page.locator("#field-demeanor").fill("Stern")
    for field in ["example_sign_images", "example_member_images"]:
        page.locator(f"#add-{field}").click()
        page.locator(f"#{field}-0-src").fill("example.svg")
        page.locator(f"#{field}-0-alt").fill(field)
    apply(page)
    assert page.evaluate("mapEditor.data.npc_groups[0].id") == "old-wardens"
    choose(page, "connections")
    page.get_by_role("button", name="Add sign", exact=True).click()
    assert page.locator("#sign-0-side").input_value() == ""
    page.locator("#sign-0-group").select_option("old-wardens")
    page.locator("#sign-0-description").fill("<b>Chipped plaque</b>")
    page.locator("#sign-0-translation").fill("Archive. Keep closed.")
    page.locator("#sign-0-side").select_option("destination")
    original = editor_server["source"].read_bytes()
    for field in ["group", "side", "description", "translation"]:
        control = page.locator(f"#sign-0-{field}")
        value = control.input_value()
        if field in ["group", "side"]:
            control.select_option("")
        else:
            control.fill("")
        page.get_by_role("button", name="Save", exact=True).click()
        wait_idle(page)
        assert editor_server["source"].read_bytes() == original
        assert not control.evaluate("input => input.checkValidity()")
        if field in ["group", "side"]:
            control.select_option(value)
        else:
            control.fill(value)
    page.get_by_role("button", name="Add sign", exact=True).click()
    page.locator("#sign-1-group").select_option("old-wardens")
    page.locator("#sign-1-side").select_option("source")
    page.locator("#sign-1-description").fill("Paper note")
    page.locator("#sign-1-translation").fill("Second sign")
    apply(page)
    choose(page, "npc_groups")
    page.locator("#field-id").fill("wardens")
    apply(page)
    assert page.evaluate("mapEditor.data.connections[0].signs.map(sign => sign.group)") == [
        "wardens",
        "wardens",
    ]
    page.get_by_role("button", name="Delete", exact=True).click()
    assert "dependent objects" in page.locator("#form-errors").inner_text()
    page.get_by_role("button", name="Rebuild graph", exact=True).click()
    wait_idle(page)
    saved = json.loads(editor_server["source"].read_text(encoding="utf-8"))
    assert saved["npc_groups"][0]["lettering"] == "Angular runes"
    assert saved["npc_groups"][0]["language_oddities"] == "<b>Runes feel warm</b>"
    assert saved["npc_groups"][0]["known_ancestries"] == ["Dwarf", "Human"]
    assert saved["connections"][0]["signs"][0] == {
        "group": "wardens",
        "side": "destination",
        "description": "<b>Chipped plaque</b>",
        "translation": "Archive. Keep closed.",
    }
    assert len(list((editor_server["output"].parent / "assets/images").glob("*.svg"))) == 1
    page.reload()
    page.wait_for_function("window.mapEditor?.network && !window.mapEditor.busy")
    choose(page, "npc_groups")
    assert (
        page.get_by_label("Language oddities (HTML)", exact=True).input_value()
        == "<b>Runes feel warm</b>"
    )
    choose(page, "connections")
    assert page.locator("#sign-0-group").input_value() == "wardens"
    assert page.locator("#sign-0-side").input_value() == "destination"
    assert page.locator("#sign-1-side").input_value() == "source"
    page.locator(".sign-entry").nth(1).get_by_role("button", name="Remove sign", exact=True).click()
    apply(page)
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    assert len(json.loads(editor_server["source"].read_text())["connections"][0]["signs"]) == 1


@pytest.mark.parametrize("keep_picture", [False, True])
@pytest.mark.parametrize("width", [390, 1500])
def test_cancel_picture_preserves_new_room(page, editor_server, keep_picture, width):
    page.set_viewport_size({"width": width, "height": 1000})
    picture = editor_server["source"].parent / "picture.svg"
    picture.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>',
        encoding="utf-8",
    )
    original = editor_server["source"].read_bytes()
    add(page, "rooms")
    page.locator("#field-name").fill("New room")
    page.locator("#field-short_description").fill("<p>Keep this draft.</p>")
    page.locator("#field-x").fill("-250")
    page.locator("#field-y").fill("500")
    if keep_picture:
        page.locator("#add-image").click()
        page.locator("#image-0-src").fill("picture.svg")
        page.locator("#image-0-alt").fill("Room picture")
        page.locator("#image-0-caption").fill("Keep me")
    page.locator("#add-image").click()
    entry = page.locator(".image-entry").last
    assert not entry.locator("input").first.evaluate("input => input.checkValidity()")
    remove = entry.get_by_role("button", name="Remove picture", exact=True)
    assert remove.inner_text() == "×"
    entry.screenshot(path=str(editor_server["source"].parent / "picture-cancel.png"))
    remove.click()
    assert page.locator(".image-entry").count() == int(keep_picture)
    assert page.locator("#field-name").input_value() == "New room"
    assert page.locator("#field-short_description").input_value() == "<p>Keep this draft.</p>"
    assert page.evaluate("mapEditor.selection") == {"kind": "rooms", "index": None}
    assert page.evaluate("document.activeElement.id") == (
        "image-0-src" if keep_picture else "add-image"
    )
    assert editor_server["source"].read_bytes() == original
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    saved = json.loads(editor_server["source"].read_text(encoding="utf-8"))["rooms"][-1]
    assert saved["id"] == "new-room"
    assert saved["name"] == "New room"
    assert saved["short_description"] == "<p>Keep this draft.</p>"
    assert saved["position"] == {"x": -250, "y": 500}
    assert saved.get("images", []) == (
        [{"src": "picture.svg", "alt": "Room picture", "caption": "Keep me"}]
        if keep_picture
        else []
    )


def test_edit_pictures_and_new_fields_save_rebuild_reload(page, editor_server):
    picture = editor_server["source"].parent / "picture.svg"
    picture.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        '<rect width="200" height="100" fill="blue"/></svg>',
        encoding="utf-8",
    )
    for kind in ("rooms", "character_groups", "characters", "connections"):
        choose(page, kind)
        if kind != "characters":
            page.locator("#field-details").fill(f"<b>{kind} detailed text</b>")
        if kind == "character_groups":
            page.locator("#field-short_description").fill("Group hover note")
        page.get_by_role("button", name="Add picture", exact=True).click()
        page.locator("#image-0-src").fill("picture.svg")
        page.locator("#image-0-alt").fill(f"{kind} alternative text")
        page.locator("#image-0-caption").fill("<b>Plain caption</b>")
        page.wait_for_function("document.querySelector('.image-preview').naturalWidth > 0")
        page.get_by_role("button", name="Add picture", exact=True).click()
        page.locator("#image-1-src").fill("https://invalid.example/missing.png")
        page.locator(".image-entry").nth(1).get_by_role(
            "button", name="Move up", exact=True
        ).click()
        assert page.locator("#image-0-src").input_value() == "https://invalid.example/missing.png"
        page.locator(".image-entry").nth(0).get_by_role(
            "button", name="Move down", exact=True
        ).click()
        page.locator(".image-entry").nth(1).get_by_role(
            "button", name="Remove picture", exact=True
        ).click()
        apply(page)
        assert page.locator("#image-0-src").input_value() == "picture.svg"
    page.get_by_role("button", name="Rebuild graph", exact=True).click()
    wait_idle(page)
    saved = json.loads(editor_server["source"].read_text(encoding="utf-8"))
    for kind in ("rooms", "character_groups", "characters", "connections"):
        assert saved[kind][0]["images"] == [
            {
                "src": "picture.svg",
                "alt": f"{kind} alternative text",
                "caption": "<b>Plain caption</b>",
            }
        ]
        if kind != "characters":
            assert saved[kind][0]["details"] == f"<b>{kind} detailed text</b>"
    assert saved["character_groups"][0]["short_description"] == "Group hover note"
    assert len(list((editor_server["output"].parent / "assets/images").glob("*.svg"))) == 1
    page.reload()
    page.wait_for_function("window.mapEditor?.network && !window.mapEditor.busy")
    choose(page, "character_groups")
    assert page.locator("#field-short_description").input_value() == "Group hover note"
    assert page.locator("#image-0-caption").input_value() == "<b>Plain caption</b>"
    assert page.evaluate("mapEditor.network.selectionHandler.options.selectable") is True
    page.locator("#image-0-src").fill("missing.svg")
    apply(page)
    page.evaluate("""() => mapEditor.network.emit('hoverNode', {
        node: 'party', event: {clientX: 400, clientY: 300}
    })""")
    page.locator("#graph-tooltip").content_frame.get_by_text(
        "Image unavailable", exact=True
    ).wait_for()


def test_capture_default_view_preserves_form_and_reopens_editor_and_viewer(
    page, editor_server, monkeypatch, browser
):
    from pf2e_map_tracker import graph

    # Bundle the same graph library for an offline generated-viewer check.
    original_build = graph.build_network

    def offline_build(data):
        network = original_build(data)
        network.cdn_resources = "in_line"
        return network

    monkeypatch.setattr(graph, "build_network", offline_build)
    view = {"position": {"x": -333.25, "y": 112.5}, "scale": 0.5}
    original = editor_server["source"].read_bytes()
    page.evaluate("view => mapEditor.network.moveTo({...view, animation: false})", view)
    choose(page, "rooms")
    page.locator("#field-name").fill("Pending room")
    page.get_by_role("button", name="Set default view", exact=True).click()
    assert page.evaluate("mapEditor.data.defaultView") == view
    assert page.evaluate("mapEditor.formDirty")
    assert page.locator("#field-name").input_value() == "Pending room"
    assert page.locator("#save-state").inner_text() == "Unsaved changes"
    assert editor_server["source"].read_bytes() == original
    page.get_by_role("button", name="Rebuild graph", exact=True).click()
    wait_idle(page)
    saved = json.loads(editor_server["source"].read_bytes())
    assert saved["defaultView"] == view
    assert saved["rooms"][0]["name"] == "Pending room"

    page.evaluate("mapEditor.network.moveTo({position: {x: 800, y: -900}, scale: 1.5})")
    page.get_by_role("button", name="Reload", exact=True).click()
    wait_idle(page)
    assert page.evaluate("mapEditor.network.getViewPosition()") == pytest.approx(view["position"])
    assert page.evaluate("mapEditor.network.getScale()") == pytest.approx(view["scale"])
    page.reload()
    page.wait_for_function("window.mapEditor?.network && !mapEditor.busy")
    page.wait_for_function("mapEditor.network.physics.stabilized")
    assert page.evaluate("mapEditor.network.getViewPosition()") == pytest.approx(view["position"])
    assert page.evaluate("mapEditor.network.getScale()") == pytest.approx(view["scale"])

    viewer = browser.new_page()
    try:
        # Optional Bootstrap resources have no bearing on map behavior.
        viewer.route("https://**/*", lambda route: route.abort())
        viewer.goto(editor_server["output"].as_uri())
        viewer.wait_for_function("window.network && network.physics.stabilized")
        assert viewer.evaluate("network.getViewPosition()") == pytest.approx(view["position"])
        assert viewer.evaluate("network.getScale()") == pytest.approx(view["scale"])
        # Later physics updates must not restore or fit over the user's current view.
        viewer.evaluate("""() => {
            network.moveTo({position: {x: 100, y: 200}, scale: 0.8});
            document.getElementById('character-visibility').value = 'show_all';
            document.getElementById('character-visibility').dispatchEvent(new Event('change'));
        }""")
        viewer.wait_for_function("network.physics.stabilized")
        assert viewer.evaluate("network.getViewPosition()") == pytest.approx({"x": 100, "y": 200})
        assert viewer.evaluate("network.getScale()") == pytest.approx(0.8)
    finally:
        viewer.close()


def test_create_all_objects_save_rebuild_and_reload(page, editor_server, tmp_path):
    original = editor_server["source"].read_bytes()
    add(page, "rooms")
    page.locator("#field-name").fill("🛏️ Refuge")
    assert page.locator("#field-id").input_value() == "refuge"
    page.locator("#field-short_description").fill("<p><b>Warm</b> &amp; safe</p>")
    apply(page)
    assert page.evaluate("mapEditor.nodes.get('refuge').label") == "🛏️ Refuge"
    assert editor_server["source"].read_bytes() == original
    assert not editor_server["output"].exists()

    add(page, "character_groups")
    page.locator("#field-name").fill("Residents")
    page.locator("#field-location").select_option("refuge")
    apply(page)

    add(page, "characters")
    page.locator("#field-name").fill("Éowyn")
    page.locator("#field-ancestry").fill("Human")
    page.locator("#placement-mode").select_option("group")
    page.locator("#field-group").select_option("residents")
    page.locator("#field-physical_description").fill("<b>Golden hair</b>")
    apply(page)

    add(page, "connectionStatus")
    page.locator("#field-description").fill("Locked")
    page.locator("#field-line_style").select_option("dashed")
    page.locator("#field-display_color").fill("#fca311")
    apply(page)

    add(page, "connections")
    page.locator("#field-from").select_option("refuge")
    page.locator("#field-to").select_option("unknown")
    page.locator("#field-status").select_option("locked")
    page.locator("#field-direction").select_option("forward_only")
    page.locator("#field-name").fill("Hidden door")
    apply(page)
    assert page.evaluate("mapEditor.edges.get('editor-edge-2').dashes")

    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    saved = json.loads(editor_server["source"].read_bytes())
    assert saved["characters"][1]["group"] == "residents"
    assert "location" not in saved["characters"][1]
    assert "color" not in saved["rooms"][2]
    assert not editor_server["output"].exists()

    page.get_by_role("button", name="Rebuild graph", exact=True).click()
    wait_idle(page)
    assert "graph rebuilt" in page.locator("#notice").inner_text()
    assert "🛏️ Refuge" in editor_server["output"].read_text(encoding="utf-8")
    page.get_by_role("button", name="Reload", exact=True).click()
    wait_idle(page)
    choose(page, "rooms", 2)
    assert page.locator("#field-short_description").input_value() == "<p><b>Warm</b> &amp; safe</p>"
    page.screenshot(path=str(tmp_path / "editor.png"), full_page=True)


def test_id_renames_update_references_and_deletion_is_blocked(page):
    choose(page, "rooms")
    page.locator("#field-id").fill("main-hall")
    apply(page)
    assert page.evaluate("mapEditor.data.character_groups[0].location") == "main-hall"
    assert page.evaluate("mapEditor.data.connections.every(c => c.from === 'main-hall')")
    page.get_by_role("button", name="Delete", exact=True).click()
    assert "Party" in page.locator("#form-errors").inner_text()
    assert "Second route" in page.locator("#form-errors").inner_text()

    choose(page, "character_groups")
    page.locator("#field-id").fill("heroes")
    apply(page)
    assert page.evaluate("mapEditor.data.characters[0].group") == "heroes"
    page.get_by_role("button", name="Delete", exact=True).click()
    assert "Hero" in page.locator("#form-errors").inner_text()

    choose(page, "connectionStatus")
    page.locator("#field-id").fill("unlocked")
    apply(page)
    assert page.evaluate("mapEditor.data.connections.every(c => c.status === 'unlocked')")
    page.get_by_role("button", name="Delete", exact=True).click()
    assert "dependent objects" in page.locator("#form-errors").inner_text()

    choose(page, "characters")
    page.locator("#placement-mode").select_option("location")
    page.locator("#field-location").select_option("study")
    apply(page)
    assert page.evaluate("mapEditor.data.characters[0].location") == "study"
    assert page.evaluate("!('group' in mapEditor.data.characters[0])")

    choose(page, "character_groups")
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete", exact=True).click()
    wait_idle(page)
    assert page.evaluate("mapEditor.data.character_groups.length") == 0


def test_invalid_form_retains_values_graph_and_disk(page, editor_server):
    original = editor_server["source"].read_bytes()
    choose(page, "rooms")
    page.locator("#field-id").fill("study")
    apply(page)
    assert "duplicate node id" in page.locator("#form-errors").inner_text()
    assert page.locator("#field-id").input_value() == "study"
    assert page.evaluate("mapEditor.nodes.get('hall').label") == "Hall"
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    assert editor_server["source"].read_bytes() == original
    page.locator("#field-id").fill("hall")
    page.locator("#field-name").fill("")
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    assert "Complete the required fields" in page.locator("#notice").inner_text()
    assert editor_server["source"].read_bytes() == original


@pytest.mark.parametrize("shift,scale", [(False, 0.5), (True, 0.5), (False, 1)])
def test_drag_room_selects_graph_object_and_saves_coordinates(page, editor_server, shift, scale):
    page.evaluate("scale => mapEditor.network.moveTo({position: {x: -400, y: 0}, scale})", scale)
    view = page.evaluate("mapEditor.network.getViewPosition()")
    canvas = page.locator("#graph").bounding_box()
    position = page.evaluate(
        "mapEditor.network.canvasToDOM(mapEditor.network.getPositions(['hall']).hall)"
    )
    x, y = canvas["x"] + position["x"], canvas["y"] + position["y"]
    page.mouse.click(x, y)
    assert page.locator("#field-id").input_value() == "hall"
    page.mouse.move(x, y)
    page.wait_for_function("!document.getElementById('graph-tooltip').hidden")
    assert "Hall" in page.locator("#graph-tooltip").content_frame.locator("body").inner_text()
    page.mouse.move(x, y)
    if shift:
        page.keyboard.down("Shift")
    page.mouse.down()
    page.mouse.move(x + 120 * scale, y + 190 * scale, steps=10)
    expected = {"x": -280, "y": 190} if shift else {"x": -250, "y": 250}
    page.wait_for_function(
        """expected => {
        const p = mapEditor.network.getPositions(['hall']).hall;
        return Math.abs(p.x - expected.x) < 3 && Math.abs(p.y - expected.y) < 3;
    }""",
        arg=expected,
    )
    page.mouse.up()
    if shift:
        page.keyboard.up("Shift")
    wait_idle(page)
    assert page.evaluate("mapEditor.network.getScale()") == pytest.approx(scale)
    assert page.evaluate("mapEditor.network.getViewPosition()") == pytest.approx(view)
    moved = page.evaluate("mapEditor.data.rooms[0].position")
    assert moved["x"] == pytest.approx(expected["x"], abs=3)
    assert moved["y"] == pytest.approx(expected["y"], abs=3)
    assert page.evaluate("mapEditor.nodes.get('hall').fixed") == {"x": True, "y": True}
    assert page.evaluate("mapEditor.nodes.get('hall').physics") is True
    assert json.loads(editor_server["source"].read_bytes())["rooms"][0]["position"]["x"] == -400
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    assert json.loads(editor_server["source"].read_bytes())["rooms"][0]["position"] == moved


def test_shift_toggles_snapping_during_drag_and_numeric_edits_stay_exact(page):
    page.evaluate("mapEditor.network.moveTo({position: {x: -400, y: 0}, scale: 0.5})")
    canvas = page.locator("#graph").bounding_box()
    position = page.evaluate(
        "mapEditor.network.canvasToDOM(mapEditor.network.getPositions(['hall']).hall)"
    )
    x, y = canvas["x"] + position["x"], canvas["y"] + position["y"]
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 60, y + 95, steps=10)

    def wait_position(expected):
        page.wait_for_function(
            """expected => {
            const p = mapEditor.network.getPositions(['hall']).hall;
            return Math.abs(p.x - expected.x) < 3 && Math.abs(p.y - expected.y) < 3;
        }""",
            arg=expected,
        )

    wait_position({"x": -250, "y": 250})
    page.keyboard.down("Shift")
    wait_position({"x": -280, "y": 190})
    page.keyboard.up("Shift")
    wait_position({"x": -250, "y": 250})
    page.keyboard.down("Shift")
    page.mouse.up()
    page.keyboard.up("Shift")
    wait_idle(page)
    assert page.evaluate("mapEditor.data.rooms[0].position.x") == pytest.approx(-280, abs=3)
    assert page.evaluate("mapEditor.data.rooms[0].position.y") == pytest.approx(190, abs=3)
    page.locator("#field-x").fill("-333.25")
    page.locator("#field-y").fill("112.5")
    view = page.evaluate("mapEditor.network.getViewPosition()")
    scale = page.evaluate("mapEditor.network.getScale()")
    apply(page)
    assert page.evaluate("mapEditor.network.getScale()") == pytest.approx(scale)
    assert page.evaluate("mapEditor.network.getViewPosition()") == pytest.approx(view)
    assert page.evaluate("mapEditor.data.rooms[0].position") == {"x": -333.25, "y": 112.5}


def drag_physics_node(page, node_id):
    page.wait_for_function("mapEditor.network.physics.stabilized")
    origin = page.evaluate("id => mapEditor.network.getPositions([id])[id]", node_id)
    page.evaluate("origin => mapEditor.network.moveTo({position: origin, scale: 0.5})", origin)
    canvas = page.locator("#graph").bounding_box()
    point = page.evaluate(
        "id => mapEditor.network.canvasToDOM(mapEditor.network.getPositions([id])[id])", node_id
    )
    x, y = canvas["x"] + point["x"], canvas["y"] + point["y"]
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 61.5, y + 43.5, steps=10)
    page.mouse.up()
    wait_idle(page)
    return {"x": origin["x"] + 123, "y": origin["y"] + 87}


@pytest.mark.parametrize(
    "kind,node_id",
    [
        ("character_groups", "party"),
        ("characters", "__character-0"),
    ],
)
def test_drag_sets_default_position_and_clear_restores_automatic_placement(
    page, editor_server, kind, node_id
):
    original = editor_server["source"].read_bytes()
    expected = drag_physics_node(page, node_id)
    position = page.evaluate("kind => mapEditor.data[kind][0].defaultPosition", kind)
    assert position == pytest.approx(expected, abs=3)
    assert page.evaluate("id => mapEditor.nodes.get(id).seedPosition", node_id) == position
    assert page.evaluate("id => mapEditor.nodes.get(id).fixed", node_id) is False
    assert page.evaluate("id => mapEditor.nodes.get(id).physics", node_id) is True
    assert page.locator("#save-state").inner_text() == "Unsaved changes"
    assert editor_server["source"].read_bytes() == original
    page.wait_for_function("mapEditor.network.physics.stabilized")
    assert page.evaluate("kind => mapEditor.data[kind][0].defaultPosition", kind) == position
    assert page.evaluate("id => mapEditor.network.getPositions([id])[id]", node_id) != position
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    assert json.loads(editor_server["source"].read_bytes())[kind][0]["defaultPosition"] == position
    page.reload()
    page.wait_for_function("window.mapEditor?.network && !mapEditor.busy")
    assert page.evaluate("id => mapEditor.nodes.get(id).seedPosition", node_id) == position
    choose(page, kind)
    assert float(page.locator("#field-x").input_value()) == position["x"]
    page.get_by_role("button", name="Use automatic position", exact=True).click()
    apply(page)
    assert page.evaluate("kind => !('defaultPosition' in mapEditor.data[kind][0])", kind)
    assert page.evaluate("id => mapEditor.nodes.get(id).seedPosition", node_id) != position
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    assert "defaultPosition" not in json.loads(editor_server["source"].read_bytes())[kind][0]


def test_unknown_room_drag_does_not_set_a_default_position(page):
    choose(page, "connections")
    page.locator("#field-to").select_option("unknown")
    apply(page)
    before = page.evaluate("JSON.stringify(mapEditor.data)")
    drag_physics_node(page, "__unknown-0-target")
    assert page.evaluate("JSON.stringify(mapEditor.data)") == before
    assert page.evaluate("mapEditor.nodes.get('__unknown-0-target').fixed") is False


def test_rejected_physics_drag_retains_pending_form(page):
    choose(page, "characters")
    page.locator("#field-name").fill("Pending Hero")
    page.once("dialog", lambda dialog: dialog.dismiss())
    drag_physics_node(page, "party")
    assert page.locator("#field-name").input_value() == "Pending Hero"
    assert page.evaluate("mapEditor.formDirty")
    assert page.evaluate("!('defaultPosition' in mapEditor.data.character_groups[0])")
    assert page.evaluate("mapEditor.nodes.get('party').fixed") is False


def test_search_hidden_objects_parallel_edges_and_unknown_selection(page):
    page.locator("#visibility").select_option("hidden")
    assert page.evaluate("mapEditor.nodes.get('__character-0').hidden")
    page.locator("#search").fill("Hero")
    choose(page, "characters")
    assert page.locator("#field-name").input_value() == "Hero"
    page.locator("#search").fill("")
    assert page.evaluate("mapEditor.edges.get('editor-edge-0').editorRef.index") == 0
    assert page.evaluate("mapEditor.edges.get('editor-edge-1').editorRef.index") == 1
    # Dispatch the same vis-network click event emitted by a selected edge/node.
    page.evaluate("mapEditor.network.emit('click', {nodes: [], edges: ['editor-edge-1']})")
    assert page.locator("#field-name").input_value() == "Second route"
    page.locator("#field-to").select_option("unknown")
    apply(page)
    page.evaluate("mapEditor.network.emit('click', {nodes: ['__unknown-1-target'], edges: []})")
    assert page.locator("#field-to").input_value() == "unknown"
    page.evaluate("mapEditor.network.emit('click', {nodes: [], edges: ['editor-edge-2']})")
    assert page.locator("#field-name").input_value() == "Hero"


def test_external_conflict_retains_draft_and_reload_requires_confirmation(page, editor_server):
    choose(page, "rooms")
    page.locator("#field-name").fill("Draft room")
    apply(page)
    external = json.loads(editor_server["source"].read_bytes())
    external["rooms"][0]["name"] = "External room"
    external_bytes = json.dumps(external).encode("utf-8")
    editor_server["source"].write_bytes(external_bytes)
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    assert "changed outside" in page.locator("#notice").inner_text()
    assert page.evaluate("mapEditor.data.rooms[0].name") == "Draft room"
    assert page.get_by_role("button", name="Save", exact=True).is_disabled()
    assert editor_server["source"].read_bytes() == external_bytes
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Reload", exact=True).click()
    assert page.evaluate("mapEditor.data.rooms[0].name") == "Draft room"
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Reload", exact=True).click()
    wait_idle(page)
    assert page.evaluate("mapEditor.data.rooms[0].name") == "External room"
    assert page.get_by_role("button", name="Save", exact=True).is_enabled()


def test_rebuild_failure_marks_changes_saved_and_can_retry(page, editor_server, monkeypatch):
    from pf2e_map_tracker import editor

    editor_server["output"].write_text("previous graph", encoding="utf-8")
    choose(page, "rooms")
    page.locator("#field-name").fill("Pending room")

    def fail(data, output):
        raise RuntimeError("test renderer failure")

    with monkeypatch.context() as patch:
        patch.setattr(editor, "write_graph", fail)
        page.get_by_role("button", name="Rebuild graph", exact=True).click()
        wait_idle(page)
        assert "Changes saved; rebuild failed" in page.locator("#notice").inner_text()
        assert page.locator("#save-state").inner_text() == "All changes saved"
        assert editor_server["output"].read_text(encoding="utf-8") == "previous graph"
        assert (
            json.loads(editor_server["source"].read_bytes())["rooms"][0]["name"] == "Pending room"
        )
    page.get_by_role("button", name="Rebuild graph", exact=True).click()
    wait_idle(page)
    assert "graph rebuilt" in page.locator("#notice").inner_text()
    assert "Pending room" in editor_server["output"].read_text(encoding="utf-8")


def test_empty_map_can_add_a_room(page, editor_server):
    editor_server["source"].write_text("{}", encoding="utf-8")
    page.get_by_role("button", name="Reload", exact=True).click()
    wait_idle(page)
    add(page, "rooms")
    page.locator("#field-name").fill("First room")
    page.get_by_role("button", name="Save", exact=True).click()
    wait_idle(page)
    assert page.evaluate("mapEditor.nodes.get('first-room').label") == "First room"
    assert json.loads(editor_server["source"].read_bytes())["rooms"][0]["id"] == "first-room"
