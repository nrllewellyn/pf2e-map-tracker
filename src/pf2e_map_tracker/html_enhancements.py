"""Post-process generated HTML with map tracker controls."""

from importlib.resources import files
from pathlib import Path

INJECTION_MARKER = "<!-- pf2e-map-tracker-enhancements -->"


def inject_enhancements(html_path: Path) -> None:
    content = html_path.read_text(encoding="utf-8")
    if INJECTION_MARKER in content:
        return

    javascript = (
        files("pf2e_map_tracker.resources")
        .joinpath("graphEnhancements.js")
        .read_text(encoding="utf-8")
    )
    injection = f"{INJECTION_MARKER}\n<script>\n{javascript}\n</script>"
    body_index = content.lower().rfind("</body>")
    if body_index == -1:
        content = f"{content}\n{injection}\n"
    else:
        content = f"{content[:body_index]}{injection}\n{content[body_index:]}"
    html_path.write_text(content, encoding="utf-8")
