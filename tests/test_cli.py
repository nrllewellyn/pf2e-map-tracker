import json
from pathlib import Path

from pf2e_map_tracker.cli import main
from pf2e_map_tracker.models import GraphOptions, MapData

TEST_DATA = Path("tests/fixtures/test_data.json")


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


def test_exported_schemas_match_models(tmp_path: Path) -> None:
    assert main(["export-schema", "--output-dir", str(tmp_path)]) == 0

    expected_schemas = {
        "map-data.schema.json": MapData.model_json_schema(by_alias=True),
        "graph-options.schema.json": GraphOptions.model_json_schema(by_alias=True),
    }
    for filename, expected in expected_schemas.items():
        exported = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        committed = json.loads((Path("schemas") / filename).read_text(encoding="utf-8"))
        assert exported == expected
        assert committed == expected
