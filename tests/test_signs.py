"""Signs reference historical groups and share the existing image publishing rules."""

import json

import pytest
from pydantic import ValidationError

from pf2e_map_tracker.graph import build_network, write_graph
from pf2e_map_tracker.images import local_image_files
from pf2e_map_tracker.models import MapData, Sign
from pf2e_map_tracker.presentation import previous_occupant_details


@pytest.fixture
def sign_data():
    return {
        "rooms": [{"id": "hall", "name": "Hall", "position": {"x": 0, "y": 0}}],
        "previous_occupants": [
            {
                "id": "wardens",
                "name": "Old Wardens",
                "language": "Dwarven",
                "language_visual_style": "Angular runes",
                "language_oddities": "Runes feel warm to the touch",
                "signage_physical_form": "Stone plaques",
                "communication_quirks": "Warnings first",
                "known_ancestries": ["Dwarf", "Human"],
                "common_appearance": "Brass badges",
                "demeanor": "Stern",
            }
        ],
        "connectionStatus": [{"id": "open", "description": "Open"}],
        "connections": [
            {
                "from": "hall",
                "to": "unknown",
                "status": "open",
                "signs": [
                    {
                        "group": "wardens",
                        "side": "source",
                        "description": "<b>Chipped plaque</b>",
                        "translation": "Archive. Close the door.",
                    },
                    {
                        "group": "wardens",
                        "side": "destination",
                        "description": "Paper note",
                        "translation": "Quiet, please.",
                    },
                ],
            }
        ],
    }


def test_signs_and_previous_occupants_are_optional_and_round_trip(sign_data):
    data = MapData.model_validate(sign_data)
    assert MapData.model_validate_json(data.model_dump_json(by_alias=True)) == data
    assert data.previous_occupants[0].example_sign_images == []
    assert data.previous_occupants[0].example_member_images == []
    del sign_data["previous_occupants"][0]["language_oddities"]
    assert MapData.model_validate(sign_data).previous_occupants[0].language_oddities == ""
    del sign_data["connections"][0]["signs"]
    del sign_data["previous_occupants"]
    data = MapData.model_validate(sign_data)
    assert data.connections[0].signs == []
    assert data.previous_occupants == []
    assert "Signs:" not in build_network(data).edges[0]["title"]


@pytest.mark.parametrize("side", ["source", "destination"])
def test_sign_side_round_trips_through_connections_and_unknown_room_details(sign_data, side):
    sign_data["connections"][0]["signs"][0]["side"] = side
    sign_data["connections"][0]["direction"] = "backward_only"
    data = MapData.model_validate(sign_data)
    assert MapData.model_validate_json(data.model_dump_json(by_alias=True)) == data
    network = build_network(data)
    assert network.edges[0]["detail"]["fields"]["signs"][0]["side"] == side
    unknown = next(node for node in network.nodes if node["id"] == "__unknown-0-target")
    assert unknown["detail"]["fields"]["signs"][0]["side"] == side


@pytest.mark.parametrize("side", ["inside", "outside", "from", "to", "Source", "", None, 1])
def test_sign_side_rejects_ambiguous_or_invalid_values(side):
    with pytest.raises(ValidationError, match="side"):
        Sign(group="wardens", side=side, description="Plaque", translation="Archive")


@pytest.mark.parametrize("field", ["group", "side", "description", "translation"])
def test_all_sign_fields_are_required_without_defaults(sign_data, field):
    del sign_data["connections"][0]["signs"][0][field]
    with pytest.raises(ValidationError) as error:
        MapData.model_validate(sign_data)
    assert any(
        item["loc"] == ("connections", 0, "signs", 0, field) and item["type"] == "missing"
        for item in error.value.errors()
    )


@pytest.mark.parametrize("field", ["group", "side", "description", "translation"])
@pytest.mark.parametrize("value", ["", " \n\t ", None])
def test_sign_fields_reject_empty_whitespace_and_null_values(sign_data, field, value):
    sign_data["connections"][0]["signs"][0][field] = value
    with pytest.raises(ValidationError, match=field):
        MapData.model_validate(sign_data)


def test_signs_validate_references_in_separate_namespace(sign_data):
    sign_data["previous_occupants"][0]["id"] = "hall"
    for sign in sign_data["connections"][0]["signs"]:
        sign["group"] = "hall"
    assert MapData.model_validate(sign_data)
    sign_data["connections"][0]["signs"][1]["group"] = "missing"
    with pytest.raises(ValidationError, match="unknown previous occupant 'missing'.*sign #2"):
        MapData.model_validate(sign_data)
    sign_data["connections"][0]["signs"][1]["group"] = "hall"
    sign_data["previous_occupants"].append(sign_data["previous_occupants"][0].copy())
    with pytest.raises(ValidationError, match="duplicate previous occupant id 'hall'"):
        MapData.model_validate(sign_data)


@pytest.mark.parametrize("field", ["signs", "previous_occupants"])
def test_sign_collections_must_be_arrays(sign_data, field):
    target = sign_data if field == "previous_occupants" else sign_data["connections"][0]
    target[field] = None
    with pytest.raises(ValidationError, match=field):
        MapData.model_validate(sign_data)


@pytest.mark.parametrize("collection", ["signs", "previous_occupants"])
def test_new_records_reject_unknown_fields(sign_data, collection):
    records = (
        sign_data[collection] if collection == "previous_occupants"
        else sign_data["connections"][0][collection]
    )
    records[0]["typo"] = "bad field"
    with pytest.raises(ValidationError, match="typo"):
        MapData.model_validate(sign_data)


def test_hover_only_reports_sign_presence_and_details_preserve_all_signs(sign_data):
    network = build_network(MapData.model_validate(sign_data))
    edge = network.edges[0]
    assert "<b>Signs:</b> 2 present" in edge["title"]
    assert all(text not in edge["title"] for text in ["Chipped plaque", "Archive", "Wardens"])
    assert edge["detail"]["fields"]["signs"] == sign_data["connections"][0]["signs"]
    unknown = next(node for node in network.nodes if node["id"] == "__unknown-0-target")
    assert unknown["detail"]["fields"]["signs"] == edge["detail"]["fields"]["signs"]


@pytest.mark.parametrize("field", ["example_sign_images", "example_member_images"])
def test_inhabitant_images_publish_with_original_metadata_and_validate_paths(
    sign_data, field, tmp_path
):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
    (tmp_path / "sample sign.svg").write_text(svg, encoding="utf-8")
    group = sign_data["previous_occupants"][0]
    group[field] = [
        {"src": "sample sign.svg", "alt": "Example", "caption": "<b>Plain caption</b>"},
        {"src": "https://invalid.example/photo.png"},
    ]
    data = MapData.model_validate(sign_data)
    assert local_image_files(data, tmp_path) == {"sample sign.svg": tmp_path / "sample sign.svg"}
    details = previous_occupant_details(data, lambda source: "resolved/" + source)
    assert details[0][field][0]["url"] == "resolved/sample sign.svg"
    assert details[0][field][0]["src"] == "sample sign.svg"
    output = tmp_path / "dist/map.html"
    write_graph(data, output, image_root=tmp_path)
    assets = list((output.parent / "assets/images").glob("*.svg"))
    assert len(assets) == 1
    html = output.read_text(encoding="utf-8")
    assert f"assets/images/{assets[0].name}" in html
    assert "https://invalid.example/photo.png" in html
    assert getattr(data.previous_occupants[0], field)[0].src == "sample sign.svg"
    previous = output.read_bytes()
    for source, message in [("missing.svg", "not found"), ("../outside.svg", "escapes")]:
        group[field][0]["src"] = source
        with pytest.raises(ValueError, match=rf"previous_occupants\[0\].{field}\[0\].*{message}"):
            write_graph(MapData.model_validate(sign_data), output, image_root=tmp_path)
        assert output.read_bytes() == previous


def test_inhabitant_html_is_encoded_safely_inside_generated_script(sign_data, tmp_path):
    sign_data["previous_occupants"][0]["demeanor"] = '</script><p>Unusual 🛡️</p>'
    output = write_graph(MapData.model_validate(sign_data), tmp_path / "map.html")
    html = output.read_text(encoding="utf-8")
    payload = html.split("const PF2E_MAP_TRACKER_PREVIOUS_OCCUPANTS = ", 1)[1].split(";\n", 1)[0]
    assert "</script>" not in payload
    assert json.loads(payload)[0]["demeanor"] == '</script><p>Unusual 🛡️</p>'
