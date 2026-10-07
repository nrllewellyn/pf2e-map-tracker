import json
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from pf2e_map_tracker import editor
from pf2e_map_tracker.cli import build_parser, main
from pf2e_map_tracker.graph import build_network
from pf2e_map_tracker.models import MapData

FIXTURE = Path(__file__).parent / "fixtures/test_data.json"
HEADERS = {"X-Map-Editor": "1", "Origin": "http://127.0.0.1:8000"}


@pytest.fixture
def session(tmp_path):
    source = tmp_path / "map.json"
    source.write_bytes(FIXTURE.read_bytes())
    output = tmp_path / "map.html"
    with TestClient(editor.create_app(source, output), base_url="http://127.0.0.1:8000") as client:
        yield client, source, output


def test_load_preview_and_local_assets(session):
    client, source, output = session
    original = source.read_bytes()
    result = client.get("/api/map").json()
    assert result["revision"] == editor.revision(original)
    assert result["schema"] == MapData.model_json_schema(by_alias=True)
    response = client.post("/api/preview", json={"data": result["data"]}, headers=HEADERS)
    assert response.status_code == 200
    graph = response.json()["graph"]
    model = MapData.model_validate(result["data"])
    shared = build_network(model)
    assert graph["options"] == shared.options
    assert len(graph["nodes"]) == len(shared.nodes)
    assert len(graph["edges"]) == len(shared.edges)
    for expected, actual in zip(shared.nodes, graph["nodes"], strict=True):
        assert {k: v for k, v in actual.items() if k != "editorRef"} == expected
    assert source.read_bytes() == original
    assert not output.exists()
    for path in [
        "/",
        "/editor.js",
        "/editor.css",
        "/editor-state.js",
        "/vendor/vis-network.min.js",
        "/vendor/vis-network.css",
    ]:
        assert client.get(path).status_code == 200


def test_default_view_is_saved_loaded_and_rebuilt(session):
    client, source, output = session
    loaded = client.get("/api/map").json()
    assert "defaultView" not in loaded["data"]
    view = {"position": {"x": -333.25, "y": 112.5}, "scale": 0.5}
    loaded["data"]["defaultView"] = view
    saved = client.put(
        "/api/map", json={"data": loaded["data"], "revision": loaded["revision"]}, headers=HEADERS
    )
    assert saved.status_code == 200
    assert json.loads(source.read_bytes())["defaultView"] == view
    assert client.get("/api/map").json()["data"]["defaultView"] == view
    rebuilt = client.post("/api/rebuild", json=saved.json(), headers=HEADERS)
    assert rebuilt.status_code == 200
    assert f"const PF2E_MAP_TRACKER_DEFAULT_VIEW = {json.dumps(view)};" in output.read_text(
        encoding="utf-8"
    )
    assert (
        build_network(MapData.model_validate(saved.json()["data"])).options["physics"][
            "stabilization"
        ]["fit"]
        is False
    )


def test_default_positions_survive_preview_save_and_rebuild(session):
    client, source, output = session
    loaded = client.get("/api/map").json()
    for kind, position in [
        ("character_groups", {"x": -123.5, "y": 456.25}),
        ("characters", {"x": 0, "y": 0}),
    ]:
        assert "defaultPosition" not in loaded["data"][kind][0]
        loaded["data"][kind][0]["defaultPosition"] = position
    preview = client.post("/api/preview", json={"data": loaded["data"]}, headers=HEADERS)
    assert preview.status_code == 200
    assert preview.json()["data"] == loaded["data"]
    rebuilt = client.post(
        "/api/rebuild",
        json={"data": loaded["data"], "revision": loaded["revision"]},
        headers=HEADERS,
    )
    assert rebuilt.status_code == 200
    assert json.loads(source.read_bytes()) == loaded["data"]
    assert client.get("/api/map").json()["data"] == loaded["data"]
    content = output.read_text(encoding="utf-8")
    nodes = json.loads(re.search(r"nodes = new vis.DataSet\((\[.*?\])\);", content)[1])
    by_id = {node["id"]: node for node in nodes}
    for node_id, kind in [("pathfinders", "character_groups"), ("__character-0", "characters")]:
        node = by_id[node_id]
        assert {"x": node["x"], "y": node["y"]} == loaded["data"][kind][0]["defaultPosition"]
        assert node["fixed"] is False and node["physics"] is True


def test_edge_references_cover_parallel_unknown_and_placement_edges():
    model = MapData.model_validate(
        {
            "rooms": [{"id": "room", "name": "Room", "position": {"x": 0, "y": 0}}],
            "character_groups": [{"id": "group", "name": "Group", "location": "room"}],
            "characters": [{"name": "Hero", "ancestry": "Human", "group": "group"}],
            "connectionStatus": [{"id": "open", "description": "Open"}],
            "connections": [
                {"from": "room", "to": "unknown", "status": "open"},
                {"from": "room", "to": "unknown", "status": "open"},
                {"from": "unknown", "to": "unknown", "status": "open"},
                {"from": "room", "to": "room", "status": "open"},
                {"from": "room", "to": "room", "status": "open"},
            ],
        }
    )
    graph = editor.graph_payload(model)
    assert len(graph["edges"]) == 7
    assert len({edge["id"] for edge in graph["edges"]}) == 7
    for i, edge in enumerate(graph["edges"][:5]):
        assert edge["editorRef"] == {"kind": "connections", "index": i}
    assert graph["edges"][5]["editorRef"] == {"kind": "characters", "index": 0}
    assert graph["edges"][6]["editorRef"] == {"kind": "character_groups", "index": 0}
    virtual = [node for node in graph["nodes"] if node["id"].startswith("__unknown-")]
    assert len(virtual) == 4
    assert all(node["editorRef"]["kind"] == "connections" for node in virtual)


def test_save_preserves_unicode_html_aliases_optional_fields_and_order(session):
    client, source, output = session
    loaded = client.get("/api/map").json()
    data = loaded["data"]
    data["rooms"][0]["name"] = "🛏️ Refuge"
    data["rooms"][0]["notes"] = "<p><b>Safe</b> &amp; warm</p>"
    data["characters"][0]["class"] = "Wizard"
    data["rooms"][0].pop("color", None)
    response = client.put(
        "/api/map", json={"data": data, "revision": loaded["revision"]}, headers=HEADERS
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["revision"] == editor.revision(source.read_bytes())
    assert client.get("/api/map").json()["data"] == data
    text = source.read_text(encoding="utf-8")
    assert "🛏️ Refuge" in text
    assert text.endswith("\n")
    assert "source" not in json.loads(text)["connections"][0]
    assert "class_name" not in json.loads(text)["characters"][0]
    assert "color" not in json.loads(text)["rooms"][0]
    assert not output.exists()


@pytest.mark.parametrize("endpoint", ["/api/preview", "/api/map", "/api/rebuild"])
def test_invalid_data_does_not_write(session, endpoint):
    client, source, output = session
    original = source.read_bytes()
    data = {"rooms": [{"id": "unknown", "name": "Bad", "position": {"x": 0, "y": 0}}]}
    body = {"data": data}
    method = client.post
    if endpoint != "/api/preview":
        body["revision"] = editor.revision(original)
    if endpoint == "/api/map":
        method = client.put
    response = method(endpoint, json=body, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["errors"]
    assert source.read_bytes() == original
    assert not output.exists()


def test_conflicts_block_save_and_rebuild(session):
    client, source, output = session
    loaded = client.get("/api/map").json()
    changed = source.read_bytes() + b"\n"
    source.write_bytes(changed)
    body = {"data": loaded["data"], "revision": loaded["revision"]}
    for method, endpoint in [(client.put, "/api/map"), (client.post, "/api/rebuild")]:
        assert method(endpoint, json=body, headers=HEADERS).status_code == 409
    assert source.read_bytes() == changed
    assert not output.exists()


def test_rebuild_uses_saved_snapshot(session):
    client, source, output = session
    loaded = client.get("/api/map").json()
    loaded["data"]["rooms"][0]["name"] = "Changed room"
    response = client.post(
        "/api/rebuild",
        json={"data": loaded["data"], "revision": loaded["revision"]},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["saved"]
    assert "Changed room" in output.read_text(encoding="utf-8")
    assert json.loads(source.read_bytes())["rooms"][0]["name"] == "Changed room"
    assert not list(output.parent.glob(".*.html"))


@pytest.mark.parametrize("failure", [OSError("disk failure"), RuntimeError("renderer failure")])
def test_rebuild_failure_returns_saved_revision_and_retains_html(session, monkeypatch, failure):
    client, source, output = session
    loaded = client.get("/api/map").json()
    output.write_text("previous graph", encoding="utf-8")
    loaded["data"]["rooms"][0]["name"] = "Saved despite failure"

    def fail(data, path):
        path.write_text("partial graph", encoding="utf-8")
        raise failure

    monkeypatch.setattr(editor, "write_graph", fail)
    response = client.post(
        "/api/rebuild",
        json={"data": loaded["data"], "revision": loaded["revision"]},
        headers=HEADERS,
    )
    result = response.json()
    assert response.status_code == 500
    assert result["saved"]
    assert result["message"] == "Changes saved; rebuild failed."
    assert result["revision"] == editor.revision(source.read_bytes())
    assert output.read_text(encoding="utf-8") == "previous graph"
    assert not list(output.parent.glob(".*.html"))


def test_atomic_save_failure_retains_source(session, monkeypatch):
    client, source, _ = session
    original = source.read_bytes()
    loaded = client.get("/api/map").json()
    loaded["data"]["rooms"][0]["name"] = "Cannot save"

    def fail_replace(self, target):
        raise PermissionError("file locked")

    monkeypatch.setattr(Path, "replace", fail_replace)
    response = client.put(
        "/api/map", json={"data": loaded["data"], "revision": loaded["revision"]}, headers=HEADERS
    )
    assert response.status_code == 500
    assert source.read_bytes() == original
    assert not list(source.parent.glob(".*.tmp"))


def test_temporary_file_lock_is_retried(session, monkeypatch):
    client, source, _ = session
    loaded = client.get("/api/map").json()
    loaded["data"]["rooms"][0]["name"] = "Saved after retry"
    original_replace = Path.replace
    attempts = []

    def briefly_locked(self, target):
        attempts.append(self)
        if len(attempts) == 1:
            raise PermissionError("brief lock")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", briefly_locked)
    response = client.put(
        "/api/map", json={"data": loaded["data"], "revision": loaded["revision"]}, headers=HEADERS
    )
    assert response.status_code == 200
    assert len(attempts) == 2
    assert json.loads(source.read_bytes())["rooms"][0]["name"] == "Saved after retry"


def test_external_edit_during_file_lock_is_preserved(session, monkeypatch):
    client, source, _ = session
    original = source.read_bytes()
    loaded = client.get("/api/map").json()
    loaded["data"]["rooms"][0]["name"] = "Must not overwrite external edit"
    external = original + b"\n"

    def locked_then_changed(self, target):
        source.write_bytes(external)
        raise PermissionError("brief lock")

    monkeypatch.setattr(Path, "replace", locked_then_changed)
    response = client.put(
        "/api/map", json={"data": loaded["data"], "revision": loaded["revision"]}, headers=HEADERS
    )
    assert response.status_code == 409
    assert source.read_bytes() == external
    assert not list(source.parent.glob(".*.tmp"))


@pytest.mark.parametrize("content", [b"{", b'{"rooms":[{"id":"broken"}]}'])
def test_invalid_input_is_reported_without_changes(session, content):
    client, source, _ = session
    source.write_bytes(content)
    response = client.get("/api/map")
    assert response.status_code == 422
    assert source.read_bytes() == content


def test_unreadable_input_is_reported(session):
    client, source, _ = session
    source.unlink()
    response = client.get("/api/map")
    assert response.status_code == 500
    assert "File operation failed" in response.json()["message"]


def test_cross_origin_and_non_editor_requests_are_rejected(session):
    client, source, _ = session
    original = source.read_bytes()
    body = {"data": {}, "revision": editor.revision(original)}
    for headers in [
        {},
        {**HEADERS, "Origin": "https://example.com"},
        {**HEADERS, "Origin": "null"},
    ]:
        assert client.put("/api/map", json=body, headers=headers).status_code == 403
    assert client.get("/api/map", headers={"Host": "example.com"}).status_code == 400
    assert source.read_bytes() == original


def test_input_cannot_be_output(session):
    _, source, _ = session
    with pytest.raises(ValueError, match="must differ"):
        editor.create_app(source, source)


def test_editor_cli_defaults_and_launch(monkeypatch, capsys):
    args = build_parser().parse_args(["edit"])
    assert args.input == Path("data/map_data.json")
    assert args.output == Path("dist/index.html")
    assert args.port == 8000
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    assert main(["edit", "--port", "8123"]) == 0
    assert calls == [{"host": "127.0.0.1", "port": 8123}]
    assert "http://127.0.0.1:8123" in capsys.readouterr().out
    assert main(["edit", "--port", "0"]) == 1


def test_missing_editor_dependency_is_actionable(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    assert main(["edit"]) == 1
    assert ".[editor]" in capsys.readouterr().err
