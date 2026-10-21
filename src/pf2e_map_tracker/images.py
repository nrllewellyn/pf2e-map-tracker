"""Resolve and publish map images without changing their authored references."""

import hashlib
import os
import tempfile
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from pf2e_map_tracker.models import MapData

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
}


def validate_image_source(source: str) -> None:
    if not source or any(ord(char) < 32 for char in source):
        raise ValueError("Image source must be a non-empty path or HTTP/HTTPS URL")
    parsed = urlsplit(source)
    if parsed.scheme in {"http", "https"}:
        if not parsed.hostname or "\\" in source:
            raise ValueError("Image URL must include a host")
        return
    if parsed.scheme or parsed.netloc or PureWindowsPath(source).drive:
        raise ValueError("Image source must be a relative path or HTTP/HTTPS URL")
    if source.startswith(("/", "\\")):
        raise ValueError("Local image paths must be relative to the map JSON directory")


def is_remote_image(source: str) -> bool:
    return urlsplit(source).scheme in {"http", "https"}


def resolve_local_image(source: str, image_root: Path) -> Path:
    validate_image_source(source)
    if is_remote_image(source):
        raise ValueError("Expected a local image path")
    root = image_root.resolve()
    path = (root / source.replace("\\", "/")).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Image path escapes the map JSON directory: {source}")
    if path.suffix.lower() not in IMAGE_TYPES:
        raise ValueError(f"Unsupported image file type: {source}")
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {source} (relative to {root})")
    return path


def local_image_files(data: "MapData", image_root: Path) -> dict[str, Path]:
    result = {}
    for kind in ("rooms", "characters", "character_groups", "connections"):
        for index, item in enumerate(getattr(data, kind)):
            for image_index, picture in enumerate(item.images):
                if not is_remote_image(picture.src):
                    try:
                        result[picture.src] = resolve_local_image(picture.src, image_root)
                    except (OSError, ValueError) as error:
                        raise ValueError(
                            f"{kind}[{index}].images[{image_index}]: {error}"
                        ) from error
    return result


def publish_images(data: "MapData", image_root: Path, output_dir: Path) -> dict[str, str]:
    # Resolve every file before publishing any assets. Assets are immutable so old HTML
    # continues to work if a subsequent render or editor rebuild fails.
    sources = local_image_files(data, image_root)
    result = {}
    for source, path in sources.items():
        content = path.read_bytes()
        filename = hashlib.sha256(content).hexdigest() + path.suffix.lower()
        relative = Path("assets/images") / filename
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            fd, name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
            temporary = Path(name)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        result[source] = relative.as_posix()
    return result
