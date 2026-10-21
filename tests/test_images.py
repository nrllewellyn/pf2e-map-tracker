import json

import pytest
from pydantic import ValidationError

from pf2e_map_tracker.cli import main
from pf2e_map_tracker.graph import build_network, generate_graph, write_graph
from pf2e_map_tracker.images import local_image_files, publish_images, resolve_local_image
from pf2e_map_tracker.models import MapData, MapImage

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
    '<rect width="400" height="200" fill="blue"/></svg>'
)


@pytest.fixture
def image_map(tmp_path):
    data = {
        "rooms": [
            {
                "id": "room",
                "name": "Room",
                "position": {"x": 0, "y": 0},
                "notes": "Room note",
                "details": "Room secret",
            }
        ],
        "character_groups": [
            {
                "id": "party",
                "name": "Party",
                "location": "room",
                "notes": "Group note",
                "details": "Group secret",
            }
        ],
        "characters": [
            {
                "name": "Hero",
                "ancestry": "Human",
                "group": "party",
                "physical_description": "Physical secret",
                "personality": "Personality secret",
                "other_details": "Other secret",
            }
        ],
        "connections": [
            {
                "from": "room",
                "to": "unknown",
                "status": "open",
                "notes": "Connection note",
                "details": "Connection secret",
            },
            {"from": "room", "to": "unknown", "status": "open", "name": "Second"},
        ],
        "connectionStatus": [{"id": "open", "description": "Open", "display_color": "red"}],
    }
    pictures = tmp_path / "pictures"
    pictures.mkdir()
    (pictures / "one picture.svg").write_text(SVG, encoding="utf-8")
    (pictures / "two.svg").write_text(SVG.replace("blue", "green"), encoding="utf-8")
    for kind in ("rooms", "characters", "character_groups", "connections"):
        data[kind][0]["images"] = [
            {"src": "pictures/one picture.svg", "alt": 'Alt " & text', "caption": "<b>Caption</b>"},
            {"src": "pictures/two.svg"},
        ]
    source = tmp_path / "map.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    return source, MapData.model_validate(data)


@pytest.mark.parametrize(
    "source",
    [
        "",
        "  ",
        "javascript:alert(1)",
        "file:///x.png",
        "ftp://example.com/x.png",
        "C:/images/x.png",
        "/x.png",
        "//example.com/x.png",
        "https:///x.png",
        "x\n.png",
    ],
)
def test_invalid_image_sources(source):
    with pytest.raises(ValidationError):
        MapImage(src=source)


def test_image_defaults_order_and_strict_fields(image_map):
    _, data = image_map
    assert [image.src for image in data.rooms[0].images] == [
        "pictures/one picture.svg",
        "pictures/two.svg",
    ]
    assert data.rooms[0].images[1].alt == data.rooms[0].images[1].caption == ""
    assert data.connections[1].images == []
    assert data.connections[1].details == ""
    with pytest.raises(ValidationError):
        MapImage(src="https://example.com/image", unexpected="field")
    assert MapImage(src="https://example.com/image").src == "https://example.com/image"


def test_hover_summaries_and_source_details(image_map):
    _, data = image_map
    graph = build_network(data)
    assert graph.select_menu is False
    assert graph.options["interaction"]["selectable"] is False
    for obj in [*graph.nodes, *graph.edges]:
        for key in ("title", "tooltip_hidden", "tooltip_groups_only", "tooltip_show_all"):
            if obj.get(key):
                assert "secret" not in obj[key]
                if obj["detail"]["images"]:
                    assert 'class="pf2e-tooltip-image"' in obj[key]
                    assert "+1 more" in obj[key]
                    assert "pictures/two.svg" not in obj[key]
                    assert "Alt &quot; &amp; text" in obj[key]
    group = next(node for node in graph.nodes if node["id"] == "party")
    assert all(
        "Group note" in group[key]
        for key in ("title", "tooltip_hidden", "tooltip_groups_only", "tooltip_show_all")
    )
    assert group["detail"]["fields"]["details"] == "Group secret"
    assert group["detail"]["members"] == ["Hero"]
    assert graph.edges[0]["id"] != graph.edges[1]["id"]
    assert graph.edges[1]["detail"]["fields"]["name"] == "Second"
    unknown = next(node for node in graph.nodes if node["id"] == "__unknown-0-target")
    assert unknown["detail"]["fields"]["details"] == "Connection secret"
    assert unknown["detail"]["appearance"]["shape"] == "box"
    assert graph.edges[-1]["detail"] is group["detail"]


def test_assets_are_relative_deduplicated_and_leave_source_unchanged(image_map, tmp_path):
    source, data = image_map
    original = source.read_bytes()
    output = tmp_path / "output folder" / "map.html"
    generate_graph(source, output)
    assets = list((output.parent / "assets/images").glob("*.svg"))
    assert len(assets) == 2
    content = output.read_text(encoding="utf-8")
    for asset in assets:
        assert f"assets/images/{asset.name}" in content
    assert "pictures/one picture.svg" in content  # Original metadata remains available.
    assert source.read_bytes() == original
    assert data.rooms[0].images[0].src == "pictures/one picture.svg"
    assert main(["validate", "--input", str(source)]) == 0


def test_collisions_and_duplicate_content(image_map):
    source, data = image_map
    other = source.parent / "other"
    other.mkdir()
    (other / "two.svg").write_text(SVG, encoding="utf-8")
    data.rooms[0].images.append(MapImage(src="other/two.svg"))
    urls = publish_images(data, source.parent, source.parent / "built")
    assert urls["other/two.svg"] == urls["pictures/one picture.svg"]
    assert urls["other/two.svg"] != urls["pictures/two.svg"]


def test_missing_or_escaping_files_do_not_replace_output(image_map, tmp_path):
    source, data = image_map
    output = tmp_path / "built/map.html"
    write_graph(data, output, image_root=source.parent)
    previous = output.read_bytes()
    previous_assets = {
        path.name: path.read_bytes() for path in (output.parent / "assets/images").iterdir()
    }
    data.rooms[0].images[0].src = "missing.svg"
    with pytest.raises(ValueError, match=r"rooms\[0\].images\[0\].*not found"):
        write_graph(data, output, image_root=source.parent)
    assert output.read_bytes() == previous
    assert all(
        (output.parent / "assets/images" / name).read_bytes() == content
        for name, content in previous_assets.items()
    )
    with pytest.raises(ValueError, match="escapes"):
        resolve_local_image("../outside.svg", source.parent)
    (tmp_path / "not-image.txt").write_text("not an image")
    with pytest.raises(ValueError, match="Unsupported"):
        resolve_local_image("not-image.txt", tmp_path)
    source.write_text(data.model_dump_json(by_alias=True), encoding="utf-8")
    assert main(["validate", "--input", str(source)]) == 1


def test_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "map"
    root.mkdir()
    outside = tmp_path / "outside.svg"
    outside.write_text(SVG, encoding="utf-8")
    try:
        (root / "link.svg").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    with pytest.raises(ValueError, match="escapes"):
        resolve_local_image("link.svg", root)


def test_remote_images_are_not_downloaded(tmp_path):
    data = MapData.model_validate(
        {
            "rooms": [
                {
                    "id": "room",
                    "name": "Room",
                    "position": {"x": 0, "y": 0},
                    "images": [{"src": "https://invalid.example/image.png"}],
                }
            ]
        }
    )
    assert local_image_files(data, tmp_path) == {}
    assert publish_images(data, tmp_path, tmp_path / "built") == {}
    assert not (tmp_path / "built").exists()


def test_editor_image_previews_round_trip_and_failed_rebuild(image_map):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from pf2e_map_tracker.editor import create_app

    source, _ = image_map
    output = source.parent / "dist/index.html"
    headers = {"X-Map-Editor": "1"}
    with TestClient(create_app(source, output), base_url="http://127.0.0.1:8000") as client:
        loaded = client.get("/api/map").json()
        preview = client.post("/api/preview", json={"data": loaded["data"]}, headers=headers)
        assert preview.status_code == 200
        room = preview.json()["graph"]["nodes"][0]
        url = room["detail"]["images"][0]["url"]
        assert url.startswith("/api/images?src=")
        image = client.get(url)
        assert image.status_code == 200
        assert image.headers["content-type"].startswith("image/svg+xml")
        assert image.text == SVG
        assert client.get("/api/images", params={"src": "missing.svg"}).status_code == 404
        for invalid in ("../outside.svg", "https://example.com/image.png", "map.json"):
            assert client.get("/api/images", params={"src": invalid}).status_code == 400
        loaded["data"]["character_groups"][0]["notes"] = "<b>Public group note</b>"
        request = {"data": loaded["data"], "revision": loaded["revision"]}
        rebuilt = client.post("/api/rebuild", json=request, headers=headers)
        assert rebuilt.status_code == 200
        saved = rebuilt.json()
        assert saved["data"]["rooms"][0]["images"][0]["src"] == "pictures/one picture.svg"
        assert client.get("/api/map").json()["data"] == saved["data"]
        previous = output.read_bytes()
        saved["data"]["rooms"][0]["images"][0]["src"] = "missing.svg"
        request = {"data": saved["data"], "revision": saved["revision"]}
        # A missing picture must not prevent authors from loading or editing the map.
        assert (
            client.post("/api/preview", json={"data": request["data"]}, headers=headers).status_code
            == 200
        )
        failed = client.post("/api/rebuild", json=request, headers=headers)
        assert failed.status_code == 500
        assert failed.json()["saved"] is True
        assert "rooms[0].images[0]" in failed.json()["error"]
        assert output.read_bytes() == previous
        assert (
            client.get("/api/map").json()["data"]["rooms"][0]["images"][0]["src"] == "missing.svg"
        )
