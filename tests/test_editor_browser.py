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
    server = uvicorn.Server(uvicorn.Config(create_app(source, output), log_level="error"))
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
    page.locator("#field-notes").fill("<p><b>Warm</b> &amp; safe</p>")
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
    assert page.locator("#field-notes").input_value() == "<p><b>Warm</b> &amp; safe</p>"
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
