"""The GUI's open document: rendering, word boxes, live matching previews and selection suggestions.

PyMuPDF documents aren't thread-safe and FastAPI runs sync endpoints in a thread pool, so every
access goes through ``LOCK``.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pymupdf
from pydantic import ValidationError

from ..annotate import is_notepdf, remove_notepdf_annots, span_quads
from ..apply import match_entries
from ..config import AnnotationSpec, Config, ConfigError, Entry, Style, resolve_entry
from ..matcher import Matcher, Span
from ..messages import msg_dict
from ..textindex import TEXT_FLAGS, DocText

LOCK = threading.RLock()
MAX_RENDERS = 48


class PasswordRequired(Exception):
    pass


@dataclass
class OpenDocument:
    path: Path
    password: Optional[str]
    mtime_ns: int
    doc: pymupdf.Document
    render_doc: pymupdf.Document  # a copy without NotePDF annotations, so previews don't double up
    doctext: DocText
    existing: int  # NotePDF annotations already in the file (replaced on save)
    renders: "OrderedDict[tuple[int, float], bytes]" = field(default_factory=OrderedDict)
    _words: dict[int, list[dict]] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return str(self.mtime_ns)

    def info(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "name": self.path.name,
            "version": self.version,
            "existing": self.existing,
            "encrypted": bool(self.doc.is_encrypted or self.doc.needs_pass),
            "pages": [{"width": p.rect.width, "height": p.rect.height, "rotation": p.rotation} for p in self.render_doc],
        }

    def matcher(self) -> Matcher:
        return Matcher(self.doctext, self.doc.page_count)

    def render(self, page_no: int, scale: float) -> bytes:
        key = (page_no, round(scale, 2))
        if key in self.renders:
            self.renders.move_to_end(key)
            return self.renders[key]
        pix = self.render_doc[page_no].get_pixmap(matrix=pymupdf.Matrix(key[1], key[1]), alpha=False)
        png = pix.tobytes("png")
        self.renders[key] = png
        while len(self.renders) > MAX_RENDERS:
            self.renders.popitem(last=False)
        return png

    def words(self, page_no: int) -> list[dict]:
        """Words in reading order with boxes in visible (rotated) page coordinates."""
        if page_no not in self._words:
            page = self.doc[page_no]
            rot = page.rotation_matrix
            self._words[page_no] = [
                {"text": w[4], "rect": _rect_list(pymupdf.Rect(w[:4]) * rot), "line": [w[5], w[6]], "box": list(w[:4])}
                for w in page.get_text("words", sort=False, flags=TEXT_FLAGS)  # ligatures expanded, as in DocText
            ]
        return self._words[page_no]

    def visible_rects(self, span: Span) -> list[dict]:
        hits = []
        for page_no, quads in sorted(span_quads(self.doctext, span).items()):
            rot = self.doc[page_no].rotation_matrix
            hits.append({"page": page_no, "rects": [_rect_list(q.rect * rot) for q in quads]})
        return hits

    def close(self) -> None:
        self.doc.close()
        self.render_doc.close()


def _rect_list(r: pymupdf.Rect) -> list[float]:
    r = pymupdf.Rect(r).normalize()
    return [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]


class Session:
    def __init__(self) -> None:
        self.current: Optional[OpenDocument] = None

    def open(self, path: Path, password: Optional[str] = None) -> OpenDocument:
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{path} not found")
        mtime = path.stat().st_mtime_ns
        cur = self.current
        if cur and cur.path == path and cur.mtime_ns == mtime and (password is None or cur.password == password):
            return cur
        doc = pymupdf.open(path)
        if not doc.is_pdf:
            doc.close()
            raise ConfigError(f"{path.name} is not a PDF")
        if doc.needs_pass and not doc.authenticate(password or ""):
            doc.close()
            raise PasswordRequired(str(path))
        existing = sum(1 for page in doc for a in page.annots() if is_notepdf(a))
        render_doc = pymupdf.open("pdf", doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_NONE))
        remove_notepdf_annots(render_doc)
        opened = OpenDocument(path, password, mtime, doc, render_doc, DocText.from_pdf(doc), existing)
        if cur is not None:
            cur.close()
        self.current = opened
        return opened

    def require(self, path: Optional[str], password: Optional[str] = None) -> OpenDocument:
        if path:
            return self.open(Path(path), password)
        if self.current is None:
            raise ConfigError("no PDF is open")
        return self.current


# -- previews --------------------------------------------------------------------------------------


def parse_entries(data: dict[str, Any]) -> tuple[Style, list[Optional[Entry]], list[Optional[str]]]:
    """Validate the document settings, then each entry on its own so one bad entry doesn't hide the rest."""
    top = {k: v for k, v in data.items() if k not in ("annotations", "tex", "tex_source")}
    try:
        cfg = Config.model_validate({**top, "annotations": []})
    except ValidationError as e:
        raise ConfigError(validation_message(e)) from e
    entries: list[Optional[Entry]] = []
    errors: list[Optional[str]] = []
    for i, raw in enumerate(data.get("annotations") or []):
        try:
            entries.append(resolve_entry(AnnotationSpec.model_validate(raw), cfg.defaults, i))
            errors.append(None)
        except ValidationError as e:
            entries.append(None)
            errors.append(validation_message(e))
        except ConfigError as e:
            entries.append(None)
            errors.append(str(e).split("\n", 1)[-1].strip(" -"))
    return cfg.defaults, entries, errors


def preview(opened: OpenDocument, data: dict[str, Any]) -> dict[str, Any]:
    _, entries, errors = parse_entries(data)
    valid = [e for e in entries if e is not None]
    results = {r.entry.index: r for r in match_entries(opened.matcher(), valid)}
    out = []
    for i, (entry, error) in enumerate(zip(entries, errors)):
        if entry is None:
            out.append({"index": i, "status": "invalid", "error": error, "warnings": [], "hits": []})
            continue
        res = results[i]
        out.append(
            {
                "index": i,
                "status": res.status,
                "warnings": [msg_dict(w) for w in res.warnings],
                "modes": sorted({s.mode for s in res.spans}),
                "score": min((s.score for s in res.spans), default=None),
                "hits": [hit for span in res.spans for hit in opened.visible_rects(span)],
            }
        )
    counts = {k: sum(1 for r in out if r["status"] == k) for k in ("found", "warning", "missing", "invalid")}
    return {"version": opened.version, "entries": out, "counts": counts}


def suggest_from_selection(opened: OpenDocument, page_no: int, first: int, last: int, defaults: Optional[dict] = None) -> dict:
    """Entry fields that target exactly the selected words (``pages``/``occurrence`` only when needed)."""
    words = opened.words(page_no)
    if not words:
        raise ConfigError("this page has no text")
    lo, hi = sorted((max(0, first), min(len(words) - 1, last)))
    chosen = words[lo : hi + 1]
    text = _join_words(chosen)
    entry_data: dict[str, Any] = {"text": text}

    style = Config.model_validate({"defaults": defaults or {}, "annotations": [{"text": text, "occurrence": "all"}]}).entries()[0]
    style.style.sequential = False
    matcher = opened.matcher()
    every = matcher.find(style).spans
    target = _best_overlap(opened, every, page_no, [pymupdf.Rect(w["box"]) for w in chosen])
    if target is None or len(every) <= 1:
        return {**entry_data, "matches": len(every)}

    on_page = [s for s in every if opened.doctext.chars[s.start].page == page_no]
    entry_data["pages"] = page_no + 1
    if len(on_page) > 1:
        entry_data["occurrence"] = next(k for k, s in enumerate(on_page, start=1) if s is target)
    return {**entry_data, "matches": len(every)}


def _join_words(words: list[dict]) -> str:
    parts: list[str] = []
    for k, w in enumerate(words):
        t = w["text"]
        if k and parts:
            prev = words[k - 1]
            if prev["text"].endswith("-") and prev["line"] != w["line"]:
                parts[-1] += t  # "moni-" + "tors" at a line break -> "moni-tors" (matches "monitors" too)
                continue
        parts.append(t)
    return " ".join(parts)


def _best_overlap(opened: OpenDocument, spans: list[Span], page_no: int, boxes: list[pymupdf.Rect]) -> Optional[Span]:
    best, best_hits = None, 0
    for span in spans:
        hits = 0
        for ch in opened.doctext.chars[span.start : span.end]:
            if ch.bbox is None or ch.page != page_no:
                continue
            center = pymupdf.Rect(ch.bbox)
            cx, cy = (center.x0 + center.x1) / 2, (center.y0 + center.y1) / 2
            if any(b.x0 <= cx <= b.x1 and b.y0 <= cy <= b.y1 for b in boxes):
                hits += 1
        if hits > best_hits:
            best, best_hits = span, hits
    return best


def validation_message(e: ValidationError) -> str:
    parts = []
    for err in e.errors(include_url=False):
        loc = ".".join(str(x) for x in err["loc"] if x != "annotations")
        msg = err["msg"].removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


SESSION = Session()
