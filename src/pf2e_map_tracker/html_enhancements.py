"""Post-process generated HTML with map tracker controls."""

import json
import tomllib
from datetime import datetime
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

INJECTION_MARKER = "<!-- pf2e-map-tracker-enhancements -->"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def inject_enhancements(html_path: Path) -> None:
    content = html_path.read_text(encoding="utf-8")
    if INJECTION_MARKER in content:
        return

    javascript = (
        files("pf2e_map_tracker.resources")
        .joinpath("graphEnhancements.js")
        .read_text(encoding="utf-8")
    )
    build_info = json.dumps(
        {
            "version": _program_version(),
            "builtAt": _build_timestamp(),
        }
    )
    injection = (
        f"{INJECTION_MARKER}\n<script>\n"
        f"const PF2E_MAP_TRACKER_BUILD = {build_info};\n"
        f"{javascript}\n</script>"
    )
    body_index = content.lower().rfind("</body>")
    if body_index == -1:
        content = f"{content}\n{injection}\n"
    else:
        content = f"{content[:body_index]}{injection}\n{content[body_index:]}"
    html_path.write_text(content, encoding="utf-8")


def _program_version() -> str:
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        with pyproject_path.open("rb") as pyproject:
            return tomllib.load(pyproject)["project"]["version"]
    return version("pf2e-map-tracker")


def _build_timestamp() -> str:
    built_at = datetime.now().astimezone()
    offset = built_at.strftime("%z")
    return f"{built_at:%Y-%m-%d %H:%M:%S} GMT{offset[:3]}:{offset[3:]}"
