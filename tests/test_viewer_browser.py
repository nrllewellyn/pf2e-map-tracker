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
def viewer(browser, tmp_path, monkeypatch, request):
    from pf2e_map_tracker import graph

    original_build = graph.build_network

    def offline_build(data):
        network = original_build(data)
        network.cdn_resources = "in_line"
        return network

    monkeypatch.setattr(graph, "build_network", offline_build)
    (tmp_path / "first.svg").write_text(SVG, encoding="utf-8")
    portrait = SVG.replace('width="400" height="200"', 'width="200" height="800"')
    (tmp_path / "second.svg").write_text(portrait.replace("blue", "green"), encoding="utf-8")
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
                "short_description": "Public note",
                "details": "<b>Hidden room detail</b>",
                "color": "#3175cf",
                "shape": "diamond",
                "images": images,
            },
            {
                "id": "study",
                "name": "Study",
                "position": {"x": 500, "y": 0},
                "short_description": " \n ",
                "details": "<p><br>&nbsp;</p>",
            },
        ],
        "character_groups": [
            {
                "id": "party",
                "name": "Party",
                "location": "hall",
                "short_description": "Group note",
                "details": "Private group detail",
                "images": images,
                "defaultPosition": {"x": 0, "y": 350},
            }
        ],
        "npc_groups": [
            {
                "id": "wardens",
                "name": "Old Wardens",
                "language": "Dwarven",
                "lettering": "Angular runes",
                "language_oddities": "<em>Runes feel warm</em>.\nOnly warnings glow.",
                "signage_physical_form": "Carved stone",
                "communication_quirks": "Warnings first",
                "known_ancestries": ["Dwarf", "Human"],
                "common_appearance": "Brass badges",
                "demeanor": "Stern but helpful",
                "example_sign_images": images[:2],
                "example_member_images": images[1:],
            },
            {"id": "scribes", "name": "Scribes", "language": "Common"},
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
                "short_description": "Public route",
                "details": "Secret route",
                "images": images,
                "signs": [
                    {
                        "group": "wardens",
                        "side": "source",
                        "description": "<b>Chipped plaque</b>",
                        "translation": "Archive. Keep closed.",
                    },
                    {
                        "group": "scribes",
                        "side": "destination",
                        "description": "Paper note",
                        "translation": "Quiet.",
                    },
                ],
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
    if getattr(request, "param", None) == "legacy":
        del data["npc_groups"]
        for connection in data["connections"]:
            connection.pop("signs", None)
    if getattr(request, "param", None) == "descriptions":
        for collection in ("rooms", "character_groups", "connections"):
            data[collection][0]["short_description"] = "<em>Brief description 🧭</em>\nSecond line"
    if getattr(request, "param", None) == "wrapping":
        text = "The hall opens into a quiet chamber lit by soft blue crystals. " * 80
        for collection in ("rooms", "connections"):
            data[collection][0]["details"] = f'<p id="wrapping-copy">{text}</p>'
    if getattr(request, "param", None) == "room-signs":
        data["rooms"][0]["details"] = (
            '<p>A plaque hangs beside the door.</p><map-sign group="wardens">'
            "<div data-description>Carved plaque</div>"
            "<div data-translation>Keep the door closed.</div></map-sign>"
            "<p>More information follows the sign.</p>"
        )
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
    # Viewport changes return before the viewer's resize handler updates the canvas.
    page.wait_for_function("""() => {
        const graph = document.getElementById('mynetwork');
        const canvas = graph.querySelector('canvas');
        return canvas.clientWidth === graph.clientWidth
            && canvas.clientHeight === graph.clientHeight;
    }""")
    return page.evaluate(
        """id => {
        const point = network.canvasToDOM(network.getPositions([id])[id]);
        const rect = document.querySelector('#mynetwork canvas').getBoundingClientRect();
        return {x: point.x + rect.left, y: point.y + rect.top};
    }""",
        node_id,
    )


def click_node(page, node_id):
    # Wait for asynchronous dialog cleanup before freezing satellite physics for the click.
    page.wait_for_function("network.interactionHandler.options.keyboard.enabled")
    page.evaluate("() => { network.stopSimulation(); network.redraw(); }")
    point = node_point(page, node_id)
    page.mouse.click(point["x"], point["y"])
    page.wait_for_selector("#map-details[open]")


def click_connection(page, index=0):
    page.evaluate(
        """index => {
        const original = network.getEdgeAt;
        network.getEdgeAt = () => `__connection-${index}`;
        network.emit('click', {pointer: {DOM: network.canvasToDOM({x: 250, y: 0})}});
        network.getEdgeAt = original;
    }""",
        index,
    )
    page.wait_for_selector("#map-details[open]")


@pytest.mark.parametrize("viewer", ["descriptions"], indirect=True)
@pytest.mark.parametrize("kind", ["room", "character_group", "connection"])
def test_short_description_html_and_line_breaks_in_tooltip_and_details(viewer, kind):
    page = viewer
    if kind == "connection":
        page.evaluate("""() => network.emit('hoverEdge', {edge: '__connection-0',
            event: {clientX: 400, clientY: 300}})""")
    else:
        node_id = "party" if kind == "character_group" else "hall"
        page.evaluate(
            """id => network.emit('hoverNode', {node: id,
            event: {clientX: 400, clientY: 300}})""",
            node_id,
        )
    tooltip = page.locator("#custom-vis-tooltip")
    assert tooltip.locator("em").inner_text() == "Brief description 🧭"
    assert "Second line" in tooltip.inner_text()
    assert "Notes:" not in tooltip.inner_text()

    if kind == "connection":
        click_connection(page)
    else:
        click_node(page, node_id)
    description = page.locator("#map-detail-fields > .map-short-description")
    assert description.locator("em").inner_text() == "Brief description 🧭"
    assert description.locator("br").count() == 1
    assert "Second line" in description.inner_text()
    assert description.evaluate("element => element === element.parentElement.firstElementChild")


def test_sign_hover_details_and_group_link_return_to_connection(viewer):
    page = viewer
    page.evaluate("""() => network.emit('hoverEdge', {edge: '__connection-0',
        event: {clientX: 400, clientY: 300}})""")
    tooltip = page.locator("#custom-vis-tooltip")
    assert "Signs: 2 present" in tooltip.inner_text()
    assert all(
        text not in tooltip.inner_text()
        for text in ["Chipped plaque", "Archive", "Wardens", "Source side", "Destination side"]
    )
    click_connection(page)
    signs = page.locator(".map-sign-card")
    assert signs.count() == 2
    assert signs.nth(0).locator("b").inner_text() == "Chipped plaque"
    assert "Dwarven" in signs.nth(0).inner_text()
    assert signs.nth(0).get_by_text("Entrance from Hall", exact=True).count() == 1
    assert "Archive. Keep closed." in signs.nth(0).inner_text()
    assert signs.nth(0).locator("img").count() == 1
    assert signs.nth(1).locator("img").count() == 0
    assert "Common" in signs.nth(1).inner_text()
    assert signs.nth(1).get_by_text("Entrance from Study", exact=True).count() == 1
    group = signs.nth(0).get_by_role("button", name="Old Wardens", exact=True)
    group.click()
    assert page.locator("#map-npc-group-details").is_visible()
    assert not page.locator("#map-additional-info").is_visible()
    assert page.locator("#map-npc-group-title").inner_text() == "Old Wardens"
    assert "Dwarf, Human" in page.locator("#map-npc-group-fields").inner_text()
    assert "Stern but helpful" in page.locator("#map-npc-group-fields").inner_text()
    page.get_by_role("button", name="View example signs image 1 full screen", exact=True).click()
    assert page.locator("#map-image-preview").is_visible()
    page.keyboard.press("Escape")
    assert page.locator("#map-npc-group-details").is_visible()
    page.keyboard.press("Escape")
    assert not page.locator("#map-npc-group-details").is_visible()
    assert page.locator("#map-details").is_visible()
    assert page.locator("#map-detail-title").inner_text() == "Passage"
    assert group.evaluate("button => button === document.activeElement")
    assert page.evaluate("network.interactionHandler.options.keyboard.enabled") is False
    page.keyboard.press("Escape")
    click_connection(page, 1)
    assert page.locator(".map-signs").count() == 0
    assert "signs" not in page.locator("#map-detail-fields").inner_text()


def test_additional_information_listing_details_photos_and_rotating_thumbnails(viewer):
    page = viewer
    page.clock.install()
    trigger = page.get_by_role("button", name="Additional Information", exact=True)
    trigger.click()
    listing = page.locator("#map-additional-info")
    assert listing.get_by_role("button", name="NPC Groups", exact=True).is_visible()
    assert listing.get_by_role("heading", name="NPC Groups", exact=True).is_visible()
    assert page.locator(".map-npc-group-card").count() == 2
    card = page.locator(".map-npc-group-card").nth(0)
    assert all(
        text in card.inner_text()
        for text in ["Old Wardens", "Dwarven", "Angular runes", "Carved stone", "Warnings first"]
    )
    assert "Brass badges" not in listing.inner_text()
    assert "Runes feel warm" not in listing.inner_text()
    thumbnail = card.locator(".map-rotating-picture img")
    first = thumbnail.get_attribute("src")
    page.clock.fast_forward(4600)
    assert thumbnail.get_attribute("src") != first
    trigger_details = card.get_by_role("button", name="Details for Old Wardens", exact=True)
    trigger_details.click()
    details = page.get_by_role("dialog", name="Old Wardens", exact=True)
    assert details.is_visible()
    assert listing.is_visible()
    assert listing.locator(".map-npc-group-card").count() == 2
    assert "Brass badges" in page.locator("#map-npc-group-fields").inner_text()
    fields = page.locator("#map-npc-group-fields")
    assert fields.locator("dt").all_text_contents()[:4] == [
        "Language",
        "Lettering",
        "Language Oddities",
        "Signage Form",
    ]
    oddities = fields.locator(".map-detail-field").nth(2).locator("dd")
    assert oddities.inner_text() == "Runes feel warm.\nOnly warnings glow."
    assert oddities.locator("em").inner_text() == "Runes feel warm"
    assert page.locator(".map-npc-group-gallery").count() == 2
    assert page.locator(".map-npc-group-gallery button").count() == 4
    assert (
        page.locator(".map-npc-group-gallery figcaption").first.inner_text()
        == "<b>Plain caption</b>"
    )
    picture = details.get_by_role(
        "button", name="View example signs image 1 full screen", exact=True
    )
    picture.click()
    assert page.locator("#map-image-preview").is_visible()
    page.keyboard.press("Escape")
    assert not page.locator("#map-image-preview").is_visible()
    assert details.is_visible()
    assert listing.is_visible()
    assert picture.evaluate("button => button === document.activeElement")
    for _ in range(8):
        page.keyboard.press("Tab")
        assert details.evaluate("dialog => dialog.contains(document.activeElement)")
    details.get_by_role("button", name="Close details", exact=True).click()
    assert not details.is_visible()
    assert listing.is_visible()
    assert trigger_details.evaluate("button => button === document.activeElement")
    page.get_by_role("button", name="Scribes", exact=True).click()
    assert page.locator("#map-npc-group-title").inner_text() == "Scribes"
    assert "Language Oddities" not in page.locator("#map-npc-group-fields").inner_text()
    assert page.locator(".map-npc-group-gallery").count() == 0
    page.keyboard.press("Escape")
    assert not page.locator("#map-npc-group-details").is_visible()
    assert listing.is_visible()
    for _ in range(8):
        page.keyboard.press("Tab")
        assert listing.evaluate("dialog => dialog.contains(document.activeElement)")
    page.locator("#map-additional-close").click()
    page.wait_for_function("network.interactionHandler.options.keyboard.enabled")
    assert trigger.evaluate("button => button === document.activeElement")
    assert page.evaluate("network.interactionHandler.options.keyboard.enabled") is True
    # Connection thumbnails cycle independently and only use example signs.
    click_connection(page)
    thumbnail = page.locator(".map-sign-card").first.locator("img")
    first = thumbnail.get_attribute("src")
    page.clock.fast_forward(4600)
    assert thumbnail.get_attribute("src") != first


@pytest.mark.parametrize("method", ["button", "escape", "backdrop"])
def test_npc_group_details_close_preserves_listing_and_focus(viewer, method):
    page = viewer
    page.set_viewport_size({"width": 1400, "height": 500})
    page.get_by_role("button", name="Additional Information", exact=True).click()
    listing = page.locator("#map-additional-info")
    trigger = listing.get_by_role("button", name="Details for Scribes", exact=True)
    trigger.scroll_into_view_if_needed()
    trigger.focus()
    before = listing.evaluate("dialog => ({html: dialog.innerHTML, scroll: dialog.scrollTop})")
    assert before["scroll"] > 0
    trigger.click()
    details = page.get_by_role("dialog", name="Scribes", exact=True)
    assert details.is_visible()
    assert listing.is_visible()
    assert listing.inner_html() == before["html"]
    if method == "button":
        details.get_by_role("button", name="Close details", exact=True).click()
    elif method == "escape":
        page.keyboard.press("Escape")
    else:
        page.mouse.click(1, 1)
    assert not details.is_visible()
    assert listing.is_visible()
    assert listing.inner_html() == before["html"]
    assert listing.evaluate("dialog => dialog.scrollTop") == pytest.approx(before["scroll"])
    assert trigger.evaluate("button => button === document.activeElement")
    assert page.evaluate("network.interactionHandler.options.keyboard.enabled") is False
    listing.get_by_role("button", name="Close", exact=True).click()
    page.wait_for_function("network.interactionHandler.options.keyboard.enabled")


def test_additional_information_small_screen_and_reduced_motion(viewer):
    page = viewer
    page.set_viewport_size({"width": 390, "height": 700})
    page.emulate_media(reduced_motion="reduce")
    page.clock.install()
    page.get_by_role("button", name="Additional Information", exact=True).click()
    modal = page.locator("#map-additional-info")
    bounds = modal.bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
    assert bounds["height"] <= 700
    assert modal.evaluate("dialog => dialog.scrollWidth <= dialog.clientWidth")
    thumbnail = page.locator(".map-rotating-picture img").first
    first = thumbnail.get_attribute("src")
    page.clock.fast_forward(10000)
    assert thumbnail.get_attribute("src") == first
    page.get_by_role("button", name="Details for Old Wardens", exact=True).click()
    details = page.locator("#map-npc-group-details")
    bounds = details.bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
    assert bounds["height"] <= 700
    assert details.evaluate("dialog => dialog.scrollWidth <= dialog.clientWidth")
    page.mouse.click(1, 1)
    assert not details.is_visible()
    assert modal.is_visible()
    page.mouse.click(1, 1)
    assert not modal.is_visible()


@pytest.mark.parametrize("viewer", ["legacy"], indirect=True)
def test_existing_maps_without_signs_or_npc_groups_still_open(viewer):
    page = viewer
    page.get_by_role("button", name="Additional Information", exact=True).click()
    assert "No NPC groups have been recorded." in page.locator("#map-additional-info").inner_text()
    page.keyboard.press("Escape")
    click_connection(page)
    assert page.locator("#map-detail-title").inner_text() == "Passage"
    assert page.locator(".map-signs").count() == 0


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
    assert page.locator("#map-image-metadata").is_hidden()
    page.locator("#map-image-details > summary").click()
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
    assert page.locator("#map-detail-title").inner_text() == "Study"
    assert page.locator("#map-detail-gallery").is_hidden()
    assert fields.locator("dt").all_text_contents() == []
    assert fields.locator(".map-short-description").count() == 0
    assert "Not set" not in page.locator("#map-details").inner_text()
    page.get_by_role("button", name="Close", exact=True).click()
    assert not page.locator("#map-details").is_visible()


@pytest.mark.parametrize("viewer", ["wrapping"], indirect=True)
@pytest.mark.parametrize("kind", ["room", "connection"])
@pytest.mark.parametrize("viewport", [(1400, 1000), (390, 700)])
def test_text_wraps_beside_right_gallery_and_below_it(viewer, kind, viewport, tmp_path):
    page = viewer
    width, height = viewport
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate("network.moveTo({position: {x: 0, y: 0}, scale: 0.5, animation: false})")
    if kind == "room":
        click_node(page, "hall")
    else:
        click_connection(page)
    page.wait_for_function("document.getElementById('map-detail-image').naturalWidth > 0")
    geometry = page.evaluate("""() => {
        const body = document.querySelector('#map-details .map-dialog-body');
        const bounds = body.getBoundingClientRect();
        const style = getComputedStyle(body);
        const range = document.createRange();
        range.selectNodeContents(document.getElementById('wrapping-copy'));
        const dialog = document.getElementById('map-details');
        return {
            left: bounds.left + parseFloat(style.paddingLeft),
            right: bounds.right - parseFloat(style.paddingRight),
            gallery: document.getElementById('map-detail-gallery').getBoundingClientRect().toJSON(),
            lines: Array.from(range.getClientRects(), rect => rect.toJSON()),
            overflow: dialog.scrollWidth > dialog.clientWidth,
        };
    }""")
    gallery = geometry["gallery"]
    assert not geometry["overflow"]
    assert gallery["right"] == pytest.approx(geometry["right"], abs=1)
    if width > 700:
        assert gallery["left"] > (geometry["left"] + geometry["right"]) / 2
        beside = [line for line in geometry["lines"] if line["top"] < gallery["bottom"]]
        below = [line for line in geometry["lines"] if line["top"] >= gallery["bottom"] + 20]
        assert beside and below
        assert all(line["right"] <= gallery["left"] - 23 for line in beside)
        assert any(line["right"] > gallery["left"] + gallery["width"] / 2 for line in below)
        assert all(line["left"] == pytest.approx(geometry["left"], abs=1) for line in below)
    else:
        assert gallery["left"] == pytest.approx(geometry["left"], abs=1)
        assert geometry["lines"][0]["top"] >= gallery["bottom"]
        assert all(line["right"] <= geometry["right"] + 1 for line in geometry["lines"])
    page.screenshot(path=str(tmp_path / f"gallery-{kind}-{width}.png"))


@pytest.mark.parametrize("viewer", ["room-signs"], indirect=True)
@pytest.mark.parametrize("kind", ["room", "connection"])
def test_sign_cards_span_full_width_below_gallery(viewer, kind):
    page = viewer
    if kind == "room":
        click_node(page, "hall")
    else:
        click_connection(page)
    gallery = page.locator("#map-detail-gallery").bounding_box()
    fields = page.locator("#map-detail-fields").bounding_box()
    card = page.locator("#map-details .map-sign-card").first.bounding_box()
    assert card["y"] >= gallery["y"] + gallery["height"]
    assert card["x"] == pytest.approx(fields["x"], abs=1)
    assert card["width"] == pytest.approx(fields["width"], abs=1)


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


@pytest.mark.parametrize("viewport", [(1400, 1000), (390, 700)])
def test_full_screen_image_returns_to_gallery_with_focus_and_selection(viewer, viewport):
    page = viewer
    width, height = viewport
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate("network.moveTo({position: {x: 0, y: 0}, scale: 0.5, animation: false})")
    click_node(page, "hall")
    trigger = page.get_by_role("button", name="View image full screen", exact=True)
    preview = page.get_by_role("dialog", name="Full-screen image preview", exact=True)
    enlarged = page.locator("#map-image-preview-image")
    for index in (1, 2):
        page.get_by_role("button", name=f"Show image {index}", exact=True).click()
        page.wait_for_function("document.getElementById('map-detail-image').naturalWidth > 0")
        trigger.click()
        preview.wait_for(state="visible")
        page.wait_for_function(
            "document.getElementById('map-image-preview-image').naturalWidth > 0"
        )
        assert enlarged.evaluate("img => img.src") == page.locator("#map-detail-image").evaluate(
            "img => img.src"
        )
        assert enlarged.get_attribute("alt") == page.locator("#map-detail-image").get_attribute(
            "alt"
        )
        bounds = preview.bounding_box()
        assert bounds == {"x": 0, "y": 0, "width": width, "height": height}
        image = enlarged.bounding_box()
        assert image["x"] >= 0 and image["x"] + image["width"] <= width
        assert image["y"] >= 0 and image["y"] + image["height"] <= height
        ratio = enlarged.evaluate("img => img.naturalWidth / img.naturalHeight")
        assert image["width"] / image["height"] == pytest.approx(ratio, rel=0.01)
        enlarged.click()
        assert preview.is_visible()
        page.mouse.click(1, 1)
        assert not preview.is_visible()
        assert page.locator("#map-details").is_visible()
        assert trigger.evaluate("button => button === document.activeElement")
        assert (
            page.get_by_role("button", name=f"Show image {index}", exact=True).get_attribute(
                "aria-pressed"
            )
            == "true"
        )
        # Reopen from the keyboard; Escape must close only the top dialog.
        page.keyboard.press("Enter")
        assert preview.is_visible()
        page.keyboard.press("Tab")
        assert preview.evaluate("dialog => dialog.contains(document.activeElement)")
        page.keyboard.press("Escape")
        assert not preview.is_visible()
        assert page.locator("#map-details").is_visible()
    trigger.click()
    page.get_by_role("button", name="Close image", exact=True).click()
    assert not preview.is_visible()
    page.keyboard.press("Escape")
    assert not page.locator("#map-details").is_visible()


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
    page.get_by_role("button", name="View image full screen", exact=True).click()
    assert page.locator("#map-image-preview").is_visible()
    page.mouse.click(1, 1)
    assert not page.locator("#map-image-preview").is_visible()
    assert page.locator("#map-detail-title").inner_text() == "Passage"
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
