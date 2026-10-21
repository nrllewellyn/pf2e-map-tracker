import json
from pathlib import Path

import pytest

from pf2e_map_tracker import io
from pf2e_map_tracker.cli import main
from pf2e_map_tracker.models import GraphOptions, MapData

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = REPOSITORY_ROOT / "tests/fixtures/test_data.json"


def test_validate_command(capsys) -> None:
    assert main(["validate", "--input", str(TEST_DATA)]) == 0
    assert "Valid map data" in capsys.readouterr().out


def test_build_command(tmp_path: Path) -> None:
    output = tmp_path / "map.html"
    assert main(["build", "--input", str(TEST_DATA), "--output", str(output)]) == 0
    assert output.exists()


def test_validation_failure_returns_nonzero(tmp_path: Path, capsys) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"rooms": [{"name": ""}]}', encoding="utf-8")

    assert main(["validate", "--input", str(invalid)]) == 1
    assert "Error:" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["build", "validate"])
def test_json_syntax_error_reports_source_and_context(
    command: str, tmp_path: Path, capsys, monkeypatch
) -> None:
    invalid = tmp_path / "broken-map.json"
    content = (
        '{\n  "characters": [{\n    "images": [\n      "src": "portrait.png"\n    ]\n  }]\n}\n'
    )
    invalid.write_text(content, encoding="utf-8")
    output = tmp_path / "map.html"
    output.write_text("previous map", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    args = [command, "--input", invalid.name]
    if command == "build":
        args += ["--output", str(output)]

    assert main(args) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"Error: Invalid JSON in {invalid}" in captured.err
    assert "Expecting ',' delimiter (line 4, column 12)" in captured.err
    assert '3 |     "images": [' in captured.err
    assert '4 |       "src": "portrait.png"\n  |            ^' in captured.err
    assert "5 |     ]" in captured.err
    assert "Traceback" not in captured.err
    assert invalid.read_text(encoding="utf-8") == content
    assert output.read_text(encoding="utf-8") == "previous map"


@pytest.mark.parametrize("command", ["build", "validate"])
def test_graph_options_json_error_identifies_resource(
    command: str, tmp_path: Path, capsys, monkeypatch
) -> None:
    resource = tmp_path / "graphOptions.json"
    resource.write_text('{\n  "physics": }\n', encoding="utf-8")
    monkeypatch.setattr(io, "files", lambda package: tmp_path)
    args = [command, "--input", str(TEST_DATA)]
    output = tmp_path / "map.html"
    if command == "build":
        args += ["--output", str(output)]

    assert main(args) == 1

    message = capsys.readouterr().err
    assert f"Invalid JSON in {resource}" in message
    assert "Expecting value (line 2, column 14)" in message
    assert '2 |   "physics": }\n  |              ^' in message
    assert not output.exists()


def test_exported_schemas_match_models(tmp_path: Path) -> None:
    assert main(["export-schema", "--output-dir", str(tmp_path)]) == 0

    expected_schemas = {
        "map-data.schema.json": MapData.model_json_schema(by_alias=True),
        "graph-options.schema.json": GraphOptions.model_json_schema(by_alias=True),
    }
    for filename, expected in expected_schemas.items():
        exported = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        committed = json.loads((REPOSITORY_ROOT / "schemas" / filename).read_text(encoding="utf-8"))
        assert exported == expected
        assert committed == expected
