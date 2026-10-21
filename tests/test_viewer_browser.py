"""Generated viewer workflows using bundled libraries and local image assets."""

import json

import pytest

from pf2e_map_tracker.graph import generate_graph
from pf2e_map_tracker.models import NodeShape

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
    '<rect width="400" height="200" fill="blue"/></svg>'
)


@pytest.fixture(scope="module")
def browser(request):
    if not request.config.getoption("--run-editor-browser"):
        pytest.skip("Use --run-browser to run Chromium workflows")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(timeout=20000)
        yield browser
        browser.close()


@pytest.fixture
def viewer(browser, tmp_path, monkeypatch):
    from pf2e_map_tracker import graph

    original_build = graph.build_network

    def offline_build(data):
        network = original_build(data)
        network.cdn_resources = "in_line"
        return network

    monkeypatch.setattr(graph, "build_network", offline_build)
    (tmp_path / "first.svg").write_text(SVG, encoding="utf-8")
    (tmp_path / "second.svg").write_text(SVG.replace("blue", "green"), encoding="utf-8")
    images = [
        {"src": "first.svg", "alt": "Wide room", "caption": "<b>Plain caption</b>"},
        {"src": "second.svg", "alt": "Another view", "caption": "Second picture"},
        {"src": "https://invalid.example/missing.png", "caption": "Unavailable picture"},
    ]
    data = {
        "defaultView": {"position": {"x": 250, "y": 0}, "scale": 0.8},
        "rooms": [
            {
                "id": "hall",
                "name": "Hall",
                "position": {"x": 0, "y": 0},
                "notes": "Public note",
                "details": "<b>Hidden room detail</b>",
                "color": "#3175cf",
                "shape": "diamond",
                "images": images,
            },
            {
                "id": "study",
                "name": "Study",
                "position": {"x": 500, "y": 0},
                "notes": " \n ",
                "details": "<p><br>&nbsp;</p>",
            },
        ],
        "character_groups": [
            {
                "id": "party",
                "name": "Party",
                "location": "hall",
                "notes": "Group note",
                "details": "Private group detail",
                "images": images,
                "defaultPosition": {"x": 0, "y": 350},
            }
        ],
        "characters": [
            {
                "name": "Hero",
                "ancestry": "Human",
                "group": "party",
                "images": images,
                "physical_description": "Tall hero",
                "personality": "Patient hero",
                "other_details": "<i>Secret hero</i>",
                "defaultPosition": {"x": 400, "y": 350},
            }
        ],
        "connectionStatus": [
            {
                "id": "open",
                "description": "Open passage",
                "display_color": "#cc8822",
                "line_style": "dashed",
            }
        ],
        "connections": [
            {
                "from": "hall",
                "to": "study",
                "status": "open",
                "name": "Passage",
                "notes": "Public route",
                "details": "Secret route",
                "images": images,
            },
            {
                "from": "hall",
                "to": "study",
                "status": "open",
                "name": "Second route",
                "images": images[:1],
            },
            {
                "from": "study",
                "to": "unknown",
                "status": "open",
                "name": "Unknown route",
                "details": "Unknown route detail",
                "images": images,
            },
        ],
    }
    source = tmp_path / "map.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    output = generate_graph(source, tmp_path / "dist/index.html")
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("https://**/*", lambda route: route.abort())
    page.goto(output.as_uri())
    page.wait_for_selector("#character-visibility")
    page.wait_for_function("!!document.getElementById('map-details')")
    page.evaluate("""() => {
        network.stopSimulation();
        network.moveTo({position: {x: 250, y: 0}, scale: 0.8, animation: false});
    }""")
    yield page
    page.close()
    assert not errors, errors


def node_point(page, node_id):
    return page.evaluate(
        """id => {
        const point = network.canvasToDOM(network.getPositions([id])[id]);
        const rect = document.querySelector('#mynetwork canvas').getBoundingClientRect();
        return {x: point.x + rect.left, y: point.y + rect.top};
    }""",
        node_id,
    )


def click_node(page, node_id):
    # Dialog keyboard options can restart satellite physics; click a settled, drawn target.
    page.evaluate("() => { network.stopSimulation(); network.redraw(); }")
    point = node_point(page, node_id)
    page.mouse.click(point["x"], point["y"])
    page.wait_for_selector("#map-details[open]")


def test_map_frame_and_canvas_fill_window_after_resize(viewer, tmp_path):
    page = viewer
    for width, height in [(2854, 1600), (1600, 2400), (390, 700), (1200, 360)]:
        view = page.evaluate("({position: network.getViewPosition(), scale: network.getScale()})")
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_function(
            """() => {
                const graph = document.getElementById('mynetwork').getBoundingClientRect();
                const canvas = document.querySelector('#mynetwork canvas').getBoundingClientRect();
                return Math.abs(graph.bottom - innerHeight) <= 2
                    && canvas.bottom <= graph.bottom && graph.bottom - canvas.bottom <= 2;
            }""",
            timeout=5000,
        )
        bounds = page.evaluate("""() => {
            const graph = document.getElementById('mynetwork').getBoundingClientRect();
            const toolbar = document.getElementById('map-toolbar').getBoundingClientRect();
            const canvas = document.querySelector('#mynetwork canvas').getBoundingClientRect();
            return {graphTop: graph.top, toolbarBottom: toolbar.bottom,
                canvasRight: canvas.right, canvasBottom: canvas.bottom,
                scrollWidth: document.documentElement.scrollWidth,
                scrollHeight: document.documentElement.scrollHeight};
        }""")
        assert bounds["graphTop"] == pytest.approx(bounds["toolbarBottom"], abs=1)
        assert bounds["canvasRight"] <= width
        assert bounds["canvasBottom"] <= height
        assert bounds["scrollWidth"] <= width
        assert bounds["scrollHeight"] <= height
        assert page.evaluate("network.getViewPosition()") == pytest.approx(view["position"])
        assert page.evaluate("network.getScale()") == pytest.approx(view["scale"])
        if width == 2854:
            page.screenshot(path=str(tmp_path / "large-window.png"))


def test_click_details_replaces_highlighting_and_gallery_is_contained(viewer):
    page = viewer
    assert page.locator("#select-node").count() == 0
    assert page.get_by_text("Reset Selection", exact=True).count() == 0
    assert page.locator("#program-version").inner_text().startswith("Version")
    before = page.evaluate(
        "({view: network.getViewPosition(), scale: network.getScale(), nodes: nodes.get()})"
    )
    click_node(page, "hall")
    assert page.locator("#map-detail-title").inner_text() == "Hall"
    fields = page.locator("#map-detail-fields")
    assert "Hidden room detail" in fields.inner_text()
    assert fields.locator("b").inner_text() == "Hidden room detail"
    assert '{"x":0,"y":0}' not in fields.inner_text()
    assert fields.get_by_text("hall", exact=True).count() == 0
    assert not {"ID", "Saved position", "Default starting position"}.intersection(
        fields.locator("dt").all_text_contents()
    )
    assert "#3175cf" not in page.locator("#map-details").inner_text()
    assert "diamond" not in page.locator("#map-details").inner_text()
    assert page.locator(".map-dialog-actions .map-shape-preview").count() == 1
    assert page.locator(".map-shape-preview").get_attribute("aria-label") == "Shape: diamond"
    page.wait_for_function("document.getElementById('map-detail-image').naturalWidth > 0")
    assert page.locator("#map-detail-caption").inner_text() == "<b>Plain caption</b>"
    assert page.locator("#map-detail-caption b").count() == 0
    page.get_by_role("button", name="Show image 2", exact=True).click()
    assert page.locator("#map-detail-caption").inner_text() == "Second picture"
    assert page.locator("#map-image-metadata").inner_text().find("second.svg") >= 0
    page.get_by_role("button", name="Show image 3", exact=True).click()
    assert page.locator("#map-image-metadata dt").all_text_contents() == ["Source"]
    page.locator("#map-image-fallback").wait_for(state="visible")
    assert page.locator("#map-detail-image").is_hidden()
    assert page.evaluate("network.getSelection()") == {"nodes": [], "edges": []}
    assert page.evaluate("network.getViewPosition()") == before["view"]
    assert page.evaluate("network.getScale()") == before["scale"]
    assert page.evaluate("nodes.get()") == before["nodes"]
    page.keyboard.press("Escape")
    assert not page.locator("#map-details").is_visible()
    click_node(page, "study")
    assert page.locator("#map-detail-gallery").is_hidden()
    assert fields.locator("dt").all_text_contents() == ["Name"]
    assert "Not set" not in page.locator("#map-details").inner_text()
    page.get_by_role("button", name="Close", exact=True).click()
    assert not page.locator("#map-details").is_visible()


@pytest.mark.parametrize("shape", [None, *NodeShape], ids=["default", *NodeShape])
def test_room_appearance_draws_default_and_supported_shapes(viewer, shape):
    page = viewer
    if shape is not None:
        page.evaluate(
            """shape => {
            const room = nodes.get('study');
            room.detail.appearance.shape = shape;
            nodes.update(room);
        }""",
            shape,
        )
    click_node(page, "study")
    page.evaluate("""() => new Promise(resolve =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)))""")
    colored_pixels = page.locator(".map-shape-preview canvas").evaluate("""canvas => {
        const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
        let count = 0;
        for (let index = 0; index < pixels.length; index += 4) {
            // Antialiased text can differ slightly after alpha premultiplication.
            if (Math.abs(pixels[index] - 49) <= 2 && Math.abs(pixels[index + 1] - 117) <= 2
                && Math.abs(pixels[index + 2] - 207) <= 2 && pixels[index + 3] >= 32) count++;
        }
        return count;
    }""")
    assert colored_pixels >= 50, (
        f"Room preview is missing its colored shape: {shape or 'default box'}"
    )


def test_hover_preview_and_detailed_character_group_fields(viewer):
    page = viewer
    point = node_point(page, "hall")
    page.mouse.move(point["x"], point["y"])
    page.wait_for_function(
        "document.getElementById('custom-vis-tooltip').style.visibility === 'visible'"
    )
    tooltip = page.locator("#custom-vis-tooltip")
    assert "Public note" in tooltip.inner_text()
    assert "+2 more" in tooltip.inner_text()
    assert "Hidden room detail" not in tooltip.inner_text()
    assert tooltip.locator("img").count() == 1
    bounds = tooltip.bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 1400
    page.locator("#character-visibility").select_option("show_all")
    page.evaluate("""() => {
        network.stopSimulation();
        network.moveNode('party', 0, 350);
        network.moveNode('__character-0', 400, 350);
    }""")
    click_node(page, "__character-0")
    assert all(
        text in page.locator("#map-detail-fields").inner_text()
        for text in ("Tall hero", "Patient hero", "Secret hero", "Party")
    )
    assert "(party)" not in page.locator("#map-detail-fields").inner_text()
    assert "Default starting position" not in page.locator("#map-detail-fields").inner_text()
    assert "Class" not in page.locator("#map-detail-fields dt").all_text_contents()
    assert "Room" not in page.locator("#map-detail-fields dt").all_text_contents()
    assert "Not set" not in page.locator("#map-details").inner_text()
    page.keyboard.press("Escape")
    click_node(page, "party")
    assert all(
        text in page.locator("#map-detail-fields").inner_text()
        for text in ("Group note", "Private group detail", "Hero", "Hall")
    )
    assert "(hall)" not in page.locator("#map-detail-fields").inner_text()
    assert "ID" not in page.locator("#map-detail-fields dt").all_text_contents()
    assert "Default starting position" not in page.locator("#map-detail-fields").inner_text()


def test_connections_parallel_metadata_unknown_nodes_and_attachment_edges(viewer):
    page = viewer
    # Find a real canvas point on the first parallel connection away from either room.
    point = page.evaluate("""() => {
        const rect = document.querySelector('#mynetwork canvas').getBoundingClientRect();
        const center = network.canvasToDOM({x: 250, y: 0});
        const points = [];
        for (let y = -80; y <= 80; y++) {
            const p = {x: center.x, y: center.y + y};
            if (network.getEdgeAt(p) === '__connection-0' && network.getNodeAt(p) === undefined)
                points.push({x: rect.left + p.x, y: rect.top + p.y});
        }
        return points[Math.floor(points.length / 2)] || null;
    }""")
    assert point
    page.mouse.click(point["x"], point["y"])
    page.wait_for_selector("#map-details[open]")
    assert page.locator("#map-detail-title").inner_text() == "Passage"
    assert "Secret route" in page.locator("#map-detail-fields").inner_text()
    assert page.locator("#map-detail-fields").get_by_text("Open passage", exact=True).count() == 1
    assert page.get_by_role("heading", name="Connection status", exact=True).count() == 0
    assert "(open)" not in page.locator("#map-detail-fields").inner_text()
    assert page.locator("#map-detail-fields").get_by_text("open", exact=True).count() == 0
    assert "ID" not in page.locator("#map-detail-fields dt").all_text_contents()
    assert page.locator(".map-dialog-actions .map-line-preview").count() == 1
    assert "#cc8822" not in page.locator("#map-details").inner_text()
    page.keyboard.press("Escape")
    # Overlapping parallel paths still retain independent source records.
    page.evaluate("""() => {
        const original = network.getEdgeAt;
        network.getEdgeAt = () => '__connection-1';
        network.emit('click', {pointer: {DOM: network.canvasToDOM({x: 250, y: 0})}});
        network.getEdgeAt = original;
    }""")
    assert page.locator("#map-detail-title").inner_text() == "Second route"
    assert page.locator("#map-detail-gallery").is_visible()
    assert page.locator("#map-detail-image").is_visible()
    assert page.locator("#map-detail-caption").inner_text() == "<b>Plain caption</b>"
    assert page.locator("#map-gallery-thumbnails").is_hidden()
    page.keyboard.press("Escape")
    page.evaluate("network.moveNode('__unknown-2-target', 700, 200)")
    click_node(page, "__unknown-2-target")
    assert page.locator("#map-detail-title").inner_text() == "Unknown Room"
    assert page.locator("#map-gallery-thumbnails").is_visible()
    assert "Unknown route detail" in page.locator("#map-detail-fields").inner_text()
    assert page.locator(".map-shape-preview").get_attribute("aria-label") == "Shape: box"
    page.keyboard.press("Escape")
    page.evaluate("""() => {
        const edge = edges.get().find(edge => edge.from === 'party');
        const original = network.getEdgeAt;
        network.getEdgeAt = () => edge.id;
        network.emit('click', {pointer: {DOM: {x: 5, y: 5}}});
        network.getEdgeAt = original;
    }""")
    assert page.locator("#map-detail-title").inner_text() == "Party"


def test_small_screen_layout_focus_and_backdrop_dismissal(viewer):
    page = viewer
    page.set_viewport_size({"width": 390, "height": 700})
    page.evaluate("network.moveTo({position: {x: 0, y: 0}, scale: 0.5, animation: false})")
    click_node(page, "hall")
    bounds = page.locator("#map-details").bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
    assert bounds["height"] <= 700
    page.get_by_role("button", name="Show image 2", exact=True).scroll_into_view_if_needed()
    image = page.locator("#map-detail-image").bounding_box()
    assert image["width"] <= bounds["width"]
    for _ in range(8):
        page.keyboard.press("Tab")
        assert page.evaluate(
            "document.getElementById('map-details').contains(document.activeElement)"
        )
    page.mouse.click(1, 1)
    assert not page.locator("#map-details").is_visible()
    assert not page.evaluate(
        "document.getElementById('map-details').contains(document.activeElement)"
    )
