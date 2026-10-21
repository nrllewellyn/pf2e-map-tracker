import json
from pathlib import Path

import pytest

from pf2e_map_tracker.io import load_map_data, parse_json


@pytest.mark.parametrize(
    ("content", "location", "excerpt"),
    [
        ("", "line 1, column 1", "1 | \n  | ^"),
        ("{\n", "line 2, column 1", "1 | {\n2 | \n  | ^"),
        ("{}\n{}\n", "line 2, column 1", "2 | {}\n  | ^"),
        ('{"rooms": [}', "line 1, column 12", '1 | {"rooms": [}\n  |            ^'),
    ],
)
def test_json_errors_handle_empty_truncated_and_extra_content(content, location, excerpt):
    with pytest.raises(ValueError) as caught:
        parse_json(content, "map.json")

    message = str(caught.value)
    assert "Invalid JSON in map.json" in message
    assert location in message
    assert excerpt in message
    assert isinstance(caught.value.__cause__, json.JSONDecodeError)


def test_json_error_caret_aligns_with_tabs_and_crlf(tmp_path: Path):
    source = tmp_path / "map.json"
    content = '{\r\n\t"rooms": [}\r\n}'
    source.write_bytes(content.encode("utf-8"))

    # The editor parses its revision's raw content; the file loader normalizes CRLF.
    for parse in (lambda: parse_json(content, source), lambda: load_map_data(source)):
        with pytest.raises(ValueError) as caught:
            parse()
        message = str(caught.value)
        assert "line 2, column 12" in message
        excerpt = message.splitlines()
        index = next(i for i, line in enumerate(excerpt) if line.startswith("2 |"))
        assert excerpt[index].index("}") == excerpt[index + 1].index("^")
        assert "\t" not in message


def test_json_error_excerpt_keeps_long_line_error_visible():
    content = '{"notes": "' + "x" * 2000 + '", "rooms": [}'
    with pytest.raises(ValueError) as caught:
        parse_json(content, "map.json")

    message = str(caught.value)
    excerpt, caret = message.splitlines()[-2:]
    assert excerpt.startswith("1 | ...")
    assert '"rooms": [}' in excerpt
    assert excerpt.index("}") == caret.index("^")
    assert len(excerpt) < 140


def test_valid_json_with_unicode_is_preserved():
    assert parse_json('{"name": "🗺️ Refuge"}', "map.json") == {"name": "🗺️ Refuge"}
