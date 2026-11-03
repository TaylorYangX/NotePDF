"""LaTeX markers -> annotation entries (in memory, or as an editable YAML config)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..colors import parse_color, to_hex
from ..config import AnnotationSpec, Config, TexConfig
from ..messages import Msg
from .detex import Detexer, literal_length
from .markers import Marker, find_markers
from .reader import TexSource, read_tex

# Defaults that suit TeX-generated entries: search in source order, and recover from small
# differences between the TeX source and the rendered text.
TEX_DEFAULTS: dict[str, Any] = {"sequential": True, "fuzzy_fallback": True, "split_fallback": True}


@dataclass
class TexResult:
    specs: list[AnnotationSpec] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)  # the same entries as plain dicts (for YAML)
    notes: list[Msg] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    default_overrides: dict[str, Any] = field(default_factory=lambda: dict(TEX_DEFAULTS))


def tex_entries(tex: TexConfig) -> TexResult:
    src = read_tex(tex.main)
    markers = find_markers(src, tex.markers, tex.detect_macros)
    detexer = Detexer(src.text_macros, tex.replacements, tex.include_captions, tex.include_footnotes)
    result = TexResult(markers=markers)
    if not markers:
        names = ", ".join(_marker_label(m) for m in tex.markers)
        result.notes.append(Msg("no_markers", f"no markers found ({names})", markers=names).with_source(str(tex.main)))

    for mk in markers:
        dx = detexer.run(src.text, mk.body_start, mk.body_end)
        for pos, what in dx.skipped:
            result.notes.append(what.with_source(src.source_ref(pos)))
        segments = []
        for seg in dx.segments:
            n = literal_length(seg.text)
            if n == 0:
                result.notes.append(
                    Msg("skip_gap_only", "fragment with only math/references is not highlighted").with_source(src.source_ref(seg.pos))
                )
            elif n < tex.min_segment_chars:
                result.notes.append(
                    Msg("skip_short", f"short fragment {seg.text!r} is not highlighted", text=seg.text).with_source(src.source_ref(seg.pos))
                )
            else:
                segments.append(seg)
        if not segments:
            if not dx.skipped:
                result.notes.append(
                    Msg("marker_empty", f"marker #{mk.order} has no matchable text", n=mk.order).with_source(src.source_ref(mk.start))
                )
            continue

        comment = mk.note or _template(mk.spec.comment, mk, src)
        highlight = _highlight(mk, result.notes, src)
        comment_at = next((k for k, seg in enumerate(segments) if seg.kind in ("text", "heading")), 0)
        for k, seg in enumerate(segments):
            row: dict[str, Any] = {"text": seg.text}
            if k == comment_at and comment:
                row["comment"] = comment
            if highlight:
                row["color"] = highlight
            row.update(mk.spec.style_overrides)
            if mk.tex_color is not None:
                row["text_color"] = to_hex(mk.tex_color)
            if seg.kind in ("caption", "footnote"):
                row["sequential"] = False  # floats/footnotes are placed away from the surrounding text
            row["group"] = f"rev-{mk.order}"
            row["source"] = src.source_ref(seg.pos)
            result.rows.append(row)
            result.specs.append(AnnotationSpec.model_validate(row))
    return result


def tex_config_dict(
    tex: TexConfig,
    base: Optional[Config] = None,
    pdf: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> tuple[dict[str, Any], TexResult]:
    """A complete, editable config with the TeX entries written out (for ``notepdf tex2config``)."""
    result = tex_entries(tex)
    folder = (out_path.parent if out_path else Path.cwd()).resolve()

    def rel(p: Optional[Path]) -> Optional[str]:
        if p is None:
            return None
        target = Path(p).resolve()
        if os.path.commonpath([target, folder]) == target.anchor:  # unrelated trees: keep it absolute
            return str(target)
        return os.path.relpath(target, folder)

    defaults: dict[str, Any] = dict(result.default_overrides)
    data: dict[str, Any] = {}
    if base is not None:
        user = base.defaults.model_dump(include=base.defaults.model_fields_set)
        if "color" in user:
            user["color"] = to_hex(user["color"])
        defaults.update(user)
        if base.input and pdf is None:
            pdf = base.input
        if base.output:
            data["output"] = rel(base.output)
        if base.password:
            data["password"] = base.password
        if not base.remove_existing:
            data["remove_existing"] = False
    data = {"input": rel(pdf), **data, "defaults": defaults, "annotations": result.rows, "tex_source": tex_source_dict(tex, rel)}
    if data["input"] is None:
        del data["input"]
    return data, result


def tex_source_dict(tex: TexConfig, rel=str) -> dict[str, Any]:
    """The TeX settings as config data, so the entries can be regenerated later (``tex_source``)."""
    data = tex.model_dump(mode="json", exclude_defaults=True, exclude={"main", "markers"})
    return {"main": rel(tex.main), "markers": [m.model_dump(mode="json", exclude_none=True) for m in tex.markers], **data}


def _template(template: Optional[str], mk: Marker, src: TexSource) -> Optional[str]:
    if not template:
        return None
    path, line = src.locate(mk.start)
    values = _SafeDict(n=mk.order, file=path.name, line=line, marker=mk.name)
    return template.format_map(values)


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _highlight(mk: Marker, notes: list[str], src: TexSource) -> Optional[str]:
    h = mk.spec.highlight
    if h is None:
        return None
    if h == "tex":
        if mk.tex_color is None:
            text = f"color of '{mk.name}' is not defined in the preamble; using the default highlight"
            notes.append(Msg("color_undefined", text, name=mk.name).with_source(src.source_ref(mk.start)))
            return None
        return to_hex(mk.tex_color)
    return to_hex(parse_color(h))


def _marker_label(spec) -> str:
    if spec.color:
        return f"\\color{{{spec.color}}}"
    if spec.macro:
        return f"\\{spec.macro}"
    return f"\\begin{{{spec.env}}}"
