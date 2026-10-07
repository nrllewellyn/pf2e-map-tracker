"""Local editor API. Imported only when the optional editor is launched."""

import hashlib
import json
import os
import tempfile
import time
from importlib.resources import files
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pf2e_map_tracker.graph import build_network, write_graph
from pf2e_map_tracker.models import MapData


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: dict[str, Any]


class SaveRequest(DraftRequest):
    revision: str


class FileConflictError(ValueError):
    """The source changed after the browser loaded it."""


def revision(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def dump_map(data: MapData) -> dict[str, Any]:
    return data.model_dump(mode="json", by_alias=True, exclude_unset=True)


def graph_payload(data: MapData) -> dict[str, Any]:
    """Use the shared renderer, with source references only on the editor payload."""
    network = build_network(data)
    references = {room.id: {"kind": "rooms", "index": i} for i, room in enumerate(data.rooms)}
    references.update(
        {
            group.id: {"kind": "character_groups", "index": i}
            for i, group in enumerate(data.character_groups)
        }
    )
    references.update(
        {
            f"__character-{i}": {"kind": "characters", "index": i}
            for i in range(len(data.characters))
        }
    )
    for i in range(len(data.connections)):
        for side in ("source", "target"):
            references[f"__unknown-{i}-{side}"] = {"kind": "connections", "index": i}

    for node in network.nodes:
        node["editorRef"] = references[node["id"]]
    attachment_refs = [
        *({"kind": "characters", "index": i} for i in range(len(data.characters))),
        *({"kind": "character_groups", "index": i} for i in range(len(data.character_groups))),
    ]
    for i, edge in enumerate(network.edges):
        edge["id"] = f"editor-edge-{i}"
        edge["editorRef"] = (
            {"kind": "connections", "index": i}
            if i < len(data.connections)
            else attachment_refs[i - len(data.connections)]
        )
    return {"nodes": network.nodes, "edges": network.edges, "options": network.options}


def _replace_file(temporary: Path, path: Path, expected_revision: str | None = None) -> None:
    # Sync clients and antivirus tools can briefly lock newly written files on Windows.
    for attempt in range(6):
        if expected_revision is not None and revision(path.read_bytes()) != expected_revision:
            raise FileConflictError("The map changed outside this editor. Reload before saving.")
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def _atomic_write(path: Path, content: bytes, expected_revision: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        _replace_file(temporary, path, expected_revision)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_build(data: MapData, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{output.name}-", suffix=".html", dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        write_graph(data, temporary)
        _replace_file(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def create_app(input_path: Path, output_path: Path) -> FastAPI:
    input_path, output_path = input_path.resolve(), output_path.resolve()
    if input_path == output_path:
        raise ValueError("input and output paths must differ")
    lock = RLock()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.url.netloc}"
            if (origin is not None and origin != expected) or (
                request.headers.get("x-map-editor") != "1"
            ):
                return JSONResponse(
                    {"message": "Only same-origin editor requests are allowed."}, status_code=403
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValidationError)
    async def invalid_data(request: Request, error: ValidationError):
        return JSONResponse(
            {
                "message": "Map validation failed.",
                "errors": error.errors(
                    include_url=False, include_context=False, include_input=False
                ),
            },
            status_code=422,
        )

    @app.exception_handler(ValueError)
    async def invalid_json(request: Request, error: ValueError):
        return JSONResponse({"message": f"Unable to read map: {error}"}, status_code=422)

    @app.exception_handler(FileConflictError)
    async def file_conflict(request: Request, error: FileConflictError):
        return JSONResponse({"message": str(error)}, status_code=409)

    @app.exception_handler(OSError)
    async def file_error(request: Request, error: OSError):
        return JSONResponse({"message": f"File operation failed: {error}"}, status_code=500)

    @app.get("/api/map")
    def load():
        with lock:
            content = input_path.read_bytes()
            data = MapData.model_validate_json(content)
            return {
                "data": dump_map(data),
                "revision": revision(content),
                "schema": MapData.model_json_schema(by_alias=True),
                "input": str(input_path),
                "output": str(output_path),
            }

    @app.post("/api/preview")
    def preview(body: DraftRequest):
        data = MapData.model_validate(body.data)
        return {"data": dump_map(data), "graph": graph_payload(data)}

    def save(body: SaveRequest):
        data = MapData.model_validate(body.data)
        current = input_path.read_bytes()
        if revision(current) != body.revision:
            return JSONResponse(
                {"message": "The map changed outside this editor. Reload before saving."},
                status_code=409,
            )
        content = (json.dumps(dump_map(data), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if content != current:
            _atomic_write(input_path, content, body.revision)
        return data, {"data": dump_map(data), "revision": revision(content)}

    @app.put("/api/map")
    def save_map(body: SaveRequest):
        with lock:
            result = save(body)
            return result if isinstance(result, JSONResponse) else result[1]

    @app.post("/api/rebuild")
    def rebuild(body: SaveRequest):
        with lock:
            result = save(body)
            if isinstance(result, JSONResponse):
                return result
            data, saved = result
            try:
                _atomic_build(data, output_path)
            except Exception as error:
                # Saving has already succeeded. Even an unexpected renderer failure must
                # return the new revision so the browser can retry without a false conflict.
                return JSONResponse(
                    {
                        **saved,
                        "saved": True,
                        "message": "Changes saved; rebuild failed.",
                        "error": str(error),
                    },
                    status_code=500,
                )
            return {
                **saved,
                "saved": True,
                "message": "Changes saved; graph rebuilt.",
                "output": str(output_path),
            }

    vis_assets = files("pyvis").joinpath("templates/lib/vis-9.1.2")
    app.mount("/vendor", StaticFiles(directory=str(vis_assets)), name="vendor")
    assets = files("pf2e_map_tracker.resources").joinpath("editor")
    app.mount("/", StaticFiles(directory=str(assets), html=True), name="editor")
    return app
