"""HTTP API for the GUI (browser and desktop app). Only imported by ``notepdf gui``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import __version__
from ..apply import apply, default_output
from ..config import Config, ConfigError, TexConfig, dump_config
from ..messages import msg_dict
from ..report import report_dict
from ..tex.to_config import tex_entries, tex_source_dict
from . import files
from .session import LOCK, SESSION, PasswordRequired, parse_entries, preview, suggest_from_selection, validation_message
from .settings import GuiSettings, add_recent, load_settings, save_settings

DIST_DIR = Path(__file__).parent / "dist"
LOCAL_HOSTS = ["127.0.0.1", "localhost"]
# The desktop app loads the UI from its own origin (or the Vite dev server) and calls this API cross-origin.
TAURI_ORIGINS = ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost", "http://localhost:1421"]
PATH_KEYS = ("input", "output")

FALLBACK_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>NotePDF</title></head>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;line-height:1.5">
<h1>NotePDF</h1><p>The interface hasn't been built yet. Build it once with:</p>
<pre>cd app &amp;&amp; npm install &amp;&amp; npm run build</pre><p>then reload this page.</p></body></html>"""


class PathBody(BaseModel):
    path: str


class OpenPdfBody(BaseModel):
    path: str
    password: Optional[str] = None


class SelectionBody(BaseModel):
    page: int
    first: int
    last: int
    defaults: dict[str, Any] = {}


class ConfigBody(BaseModel):
    config: dict[str, Any]


class SaveConfigBody(BaseModel):
    path: str
    config: dict[str, Any]


class ApplyBody(BaseModel):
    config: dict[str, Any]
    output: Optional[str] = None


class TexImportBody(BaseModel):
    tex: dict[str, Any]


class OpenBody(BaseModel):
    path: str
    reveal: bool = False


def _path(raw: str) -> Path:
    try:
        return files.normalize_path(raw)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


def _absolutize(data: dict[str, Any], base: Path) -> dict[str, Any]:
    """Config data with its paths made absolute (the GUI works with absolute paths)."""
    data = dict(data)
    for key in PATH_KEYS:
        if data.get(key):
            data[key] = str((base / data[key]).resolve()) if not Path(data[key]).is_absolute() else data[key]
    for key in ("tex", "tex_source"):
        if isinstance(data.get(key), dict) and data[key].get("main"):
            main = Path(data[key]["main"])
            data[key] = {**data[key], "main": str(main if main.is_absolute() else (base / main).resolve())}
    return data


def _relativize(data: dict[str, Any], folder: Path) -> dict[str, Any]:
    """Paths relative to the config file when they share a tree with it, so the files can move together."""

    def rel(p: str) -> str:
        target = Path(p).resolve()
        if os.path.commonpath([target, folder]) == target.anchor:
            return str(target)
        return os.path.relpath(target, folder)

    data = dict(data)
    for key in PATH_KEYS:
        if data.get(key):
            data[key] = rel(data[key])
    for key in ("tex", "tex_source"):
        if isinstance(data.get(key), dict) and data[key].get("main"):
            data[key] = {**data[key], "main": rel(data[key]["main"])}
    return data


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Drop empty values the form leaves behind, so saved configs stay tidy."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        if isinstance(v, dict):
            v = _clean(v)
            if not v:
                continue
        elif isinstance(v, list):
            v = [_clean(x) if isinstance(x, dict) else x for x in v]
        out[k] = v
    return out


def _validate(data: dict[str, Any]) -> Config:
    try:
        return Config.model_validate(data)
    except ValidationError as e:
        raise HTTPException(422, validation_message(e)) from None


def create_app(allowed_hosts: Optional[list[str]] = None, app_mode: bool = False, initial: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="NotePDF", docs_url=None, redoc_url=None)
    if allowed_hosts:
        # Blocks DNS-rebinding pages from reaching the local API (which can read and write files).
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    if app_mode:
        app.add_middleware(CORSMiddleware, allow_origins=TAURI_ORIGINS, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ConfigError)
    async def config_error(_request, exc: ConfigError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(FileNotFoundError)
    async def not_found(_request, exc: FileNotFoundError):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(PasswordRequired)
    async def password_required(_request, exc: PasswordRequired):
        return JSONResponse({"detail": "password_required", "path": str(exc)}, status_code=401)

    # -- app ---------------------------------------------------------------------------------------

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        start = None
        if initial:
            p = Path(initial).resolve()
            kind = {".pdf": "pdf", ".tex": "tex", ".yaml": "config", ".yml": "config", ".json": "config"}.get(p.suffix.lower())
            start = {"path": str(p), "kind": kind} if kind else None
        return {
            "version": __version__,
            "wsl": files.is_wsl(),
            "home": str(Path.home()),
            "cwd": os.getcwd(),
            "app_mode": app_mode,
            "initial": start,
            "fuzzy": _has_fuzzy(),
        }

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return load_settings().model_dump(mode="json")

    @app.put("/api/settings")
    def put_settings(body: dict[str, Any]) -> dict[str, Any]:
        current = load_settings().model_dump(mode="json")
        try:
            merged = GuiSettings.model_validate({**current, **body})
        except ValidationError as e:
            raise HTTPException(422, str(e)) from None
        return save_settings(merged).model_dump(mode="json")

    # -- files -------------------------------------------------------------------------------------

    @app.get("/api/fs")
    def fs(path: str = Query(""), ext: str = Query(""), hidden: bool = False) -> dict[str, Any]:
        target = _path(path) if path else Path.home()
        try:
            return files.list_dir(target, [e for e in ext.split(",") if e], hidden)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from None

    @app.post("/api/path/normalize")
    def normalize(body: PathBody) -> dict[str, Any]:
        p = _path(body.path)
        return {"path": str(p), "exists": p.exists(), "is_dir": p.is_dir()}

    @app.post("/api/open")
    def open_path(body: OpenBody) -> dict[str, Any]:
        files.open_with_default_app(_path(body.path), reveal=body.reveal)
        return {"ok": True}

    # -- PDF ---------------------------------------------------------------------------------------

    @app.post("/api/pdf/open")
    def pdf_open(body: OpenPdfBody) -> dict[str, Any]:
        path = _path(body.path)
        with LOCK:
            opened = SESSION.open(path, body.password)
            info = opened.info()
        add_recent(path, "pdf")
        return info

    @app.get("/api/pdf/page/{page_no}.png")
    def pdf_page(page_no: int, scale: float = Query(1.5, ge=0.25, le=4), v: str = "") -> Response:
        with LOCK:
            opened = SESSION.require(None)
            if not 0 <= page_no < opened.doc.page_count:
                raise HTTPException(404, "no such page")
            png = opened.render(page_no, scale)
        return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/pdf/page/{page_no}/words")
    def pdf_words(page_no: int) -> dict[str, Any]:
        with LOCK:
            opened = SESSION.require(None)
            if not 0 <= page_no < opened.doc.page_count:
                raise HTTPException(404, "no such page")
            return {"page": page_no, "words": [{"text": w["text"], "rect": w["rect"]} for w in opened.words(page_no)]}

    @app.post("/api/pdf/selection")
    def pdf_selection(body: SelectionBody) -> dict[str, Any]:
        with LOCK:
            opened = SESSION.require(None)
            if not 0 <= body.page < opened.doc.page_count:
                raise HTTPException(404, "no such page")
            return suggest_from_selection(opened, body.page, body.first, body.last, body.defaults)

    # -- configs, preview, apply -------------------------------------------------------------------

    @app.post("/api/preview")
    def api_preview(body: ConfigBody) -> dict[str, Any]:
        data = body.config
        with LOCK:
            opened = SESSION.require(data.get("input"), data.get("password"))
            return preview(opened, data)

    @app.post("/api/apply")
    def api_apply(body: ApplyBody) -> dict[str, Any]:
        data = {k: v for k, v in body.config.items() if k != "tex"}
        if not data.get("input"):
            raise HTTPException(422, "no input PDF")
        _, entries, errors = parse_entries(data)
        bad = [f"#{i + 1}: {err}" for i, err in enumerate(errors) if err]
        if bad:
            raise HTTPException(422, "fix these entries first: " + "; ".join(bad))
        cfg = _validate(_clean(data))
        output = _path(body.output) if body.output else (cfg.output or default_output(Path(cfg.input)))  # type: ignore[arg-type]
        with LOCK:
            report = apply(cfg, output_pdf=output)
            SESSION.current = None if SESSION.current and SESSION.current.path == output.resolve() else SESSION.current
        result = report_dict(report)
        for row, res in zip(result["entries"], report.results):
            row["warnings"] = [msg_dict(w) for w in res.warnings]
        result["notes"] = [msg_dict(n) for n in report.notes]
        return result

    @app.post("/api/config/load")
    def config_load(body: PathBody) -> dict[str, Any]:
        path = _path(body.path)
        cfg = Config.load(path)  # validates; ConfigError -> 422
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data = _absolutize(raw, path.parent)
        notes: list[dict] = []
        converted = False
        if cfg.tex is not None:
            # The GUI edits entries directly, so entries the config would generate from LaTeX are imported once.
            result = tex_entries(cfg.tex)
            data["annotations"] = list(data.get("annotations") or []) + result.rows
            data["tex_source"] = tex_source_dict(cfg.tex)
            del data["tex"]
            notes = [msg_dict(n) for n in result.notes]
            converted = True
        add_recent(path, "config")
        return {"path": str(path), "config": data, "converted": converted, "notes": notes}

    @app.post("/api/config/save")
    def config_save(body: SaveConfigBody) -> dict[str, Any]:
        path = _path(body.path)
        if path.suffix.lower() not in (".yaml", ".yml", ".json"):
            path = path.with_suffix(".yaml")
        data = _clean(body.config)
        _validate(data)
        dump_config(_relativize(data, path.parent.resolve()), path)
        add_recent(path, "config")
        return {"path": str(path)}

    @app.post("/api/tex/import")
    def api_tex_import(body: TexImportBody) -> dict[str, Any]:
        tex_data = dict(body.tex)
        if not tex_data.get("main"):
            raise HTTPException(422, "choose the main .tex file")
        tex_data["main"] = str(_path(tex_data["main"]))
        try:
            tex = TexConfig.model_validate(_clean(tex_data))
        except ValidationError as e:
                raise HTTPException(422, validation_message(e)) from None
        result = tex_entries(tex)
        add_recent(tex.main, "tex")
        return {
            "rows": result.rows,
            "notes": [msg_dict(n) for n in result.notes],
            "markers": len(result.markers),
            "tex_source": tex_source_dict(tex),
            "defaults": result.default_overrides,
        }

    # The UI comes last, so that /api/* always wins.
    if (DIST_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="ui")
    else:

        @app.get("/", include_in_schema=False)
        async def index() -> HTMLResponse:
            return HTMLResponse(FALLBACK_HTML)

    return app


def _has_fuzzy() -> bool:
    try:
        import rapidfuzz  # noqa: F401
    except ImportError:
        return False
    return True
