"""Config models: what to annotate, how it looks, and (optionally) where to pull entries from LaTeX."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .colors import RGB, parse_color, to_hex

AnnotType = Literal["highlight", "underline", "strikeout", "squiggly"]
PageRange = tuple[int, Optional[int]]  # 1-based, inclusive; None = to the last page


class ConfigError(ValueError):
    pass


def parse_pages(value: Any) -> Optional[list[PageRange]]:
    """``3`` | ``[3, 5]`` | ``"3-5"`` | ``"7-"`` | ``"1,3-4"`` -> list of inclusive 1-based ranges."""
    if value is None:
        return None
    items = value if isinstance(value, list) else [value]
    ranges: list[PageRange] = []
    for item in items:
        parts = [item] if isinstance(item, int) else [p.strip() for p in str(item).split(",") if p.strip()]
        for part in parts:
            if isinstance(part, int):
                lo, hi = part, part
            else:
                m = re.fullmatch(r"(\d+)\s*(?:-\s*(\d*))?", part)
                if not m:
                    raise ValueError(f"invalid page spec {part!r}; use 3, [3, 5], '3-5' or '7-'")
                lo = int(m.group(1))
                hi = lo if m.group(2) is None else (int(m.group(2)) if m.group(2) else None)
            if lo < 1 or (hi is not None and hi < lo):
                raise ValueError(f"invalid page range {part!r} (pages are 1-based)")
            ranges.append((lo, hi))
    return ranges


def pages_to_indices(ranges: Optional[list[PageRange]], page_count: int) -> list[int]:
    """Resolve page ranges to sorted 0-based indices that exist in the document."""
    if ranges is None:
        return list(range(page_count))
    out: set[int] = set()
    for lo, hi in ranges:
        out.update(range(lo - 1, min(hi if hi is not None else page_count, page_count)))
    return sorted(out)


class Style(BaseModel):
    """Settings that ``defaults`` provides and any entry (or TeX marker) may override."""

    model_config = ConfigDict(extra="forbid")

    type: AnnotType = "highlight"
    color: RGB = Field(default_factory=lambda: parse_color("yellow"))
    opacity: float = Field(0.4, ge=0, le=1)
    author: Optional[str] = None
    subject: str = "NotePDF"
    match: Literal["exact", "normalized", "fuzzy"] = "normalized"
    case_sensitive: bool = False
    whole_word: bool = False
    occurrence: Union[Literal["first", "all"], int, list[int]] = "first"
    popup: Literal["closed", "open", "none"] = "closed"
    sticky_note: bool = False
    continuation_comment: str = "none"  # "none" | "same" | any literal text
    sequential: bool = False
    fuzzy_fallback: bool = False  # try fuzzy matching (needs rapidfuzz) when exact/normalized finds nothing
    split_fallback: bool = False  # if a long text isn't found, match it sentence by sentence
    fuzzy_threshold: float = Field(90, ge=0, le=100)

    @field_validator("color", mode="before")
    @classmethod
    def _color(cls, v: Any) -> RGB:
        return parse_color(v)

    @field_validator("occurrence")
    @classmethod
    def _occurrence(cls, v: Any) -> Any:
        nums = v if isinstance(v, list) else [v] if isinstance(v, int) else []
        if any(n < 1 for n in nums):
            raise ValueError("occurrence numbers are 1-based")
        return v


STYLE_FIELDS = frozenset(Style.model_fields)


def _check_style_extras(model: BaseModel, where: str) -> None:
    unknown = set(model.model_extra or {}) - STYLE_FIELDS
    if unknown:
        raise ValueError(f"unknown {where} field(s): {', '.join(sorted(unknown))}")


class AnnotationSpec(BaseModel):
    """One entry of ``annotations``. Style fields (color, opacity, ...) may appear inline as overrides."""

    model_config = ConfigDict(extra="allow")

    text: Optional[str] = None
    regex: Optional[str] = None
    comment: Optional[str] = None
    pages: Optional[list[PageRange]] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    text_color: Optional[RGB] = None  # prefer matches rendered in this text color (e.g. the TeX revcolor)
    group: Optional[str] = None
    source: Optional[str] = None
    required: bool = True

    @field_validator("pages", mode="before")
    @classmethod
    def _pages(cls, v: Any) -> Optional[list[PageRange]]:
        return parse_pages(v)

    @field_validator("text_color", mode="before")
    @classmethod
    def _text_color(cls, v: Any) -> Optional[RGB]:
        return None if v is None else parse_color(v)

    @model_validator(mode="after")
    def _check(self) -> "AnnotationSpec":
        if (self.text is None) == (self.regex is None):
            raise ValueError("each annotation needs exactly one of 'text' or 'regex'")
        if self.text is not None and not self.text.strip():
            raise ValueError("'text' is empty")
        if self.regex is not None:
            try:
                re.compile(self.regex)
            except re.error as e:
                raise ValueError(f"invalid regex {self.regex!r}: {e}") from e
        _check_style_extras(self, "annotation")
        return self


class MarkerSpec(BaseModel):
    """A LaTeX construct whose content should be highlighted."""

    model_config = ConfigDict(extra="allow")

    color: Optional[str] = None  # TeX color name: {\color{X}..}, \textcolor{X}{..}
    macro: Optional[str] = None  # \macro{..} or \macro[opt]{..} (without the backslash)
    env: Optional[str] = None  # \begin{env}..\end{env}
    highlight: Optional[Union[str, list[float]]] = None  # highlight color; "tex" = the \definecolor value
    comment: Optional[str] = None  # fallback when the marker has no %@note

    @model_validator(mode="after")
    def _check(self) -> "MarkerSpec":
        if sum(x is not None for x in (self.color, self.macro, self.env)) != 1:
            raise ValueError("each marker needs exactly one of 'color', 'macro' or 'env'")
        if self.macro is not None:
            self.macro = self.macro.lstrip("\\")
        if self.highlight is not None and self.highlight != "tex":
            parse_color(self.highlight)
        _check_style_extras(self, "marker")
        return self

    @property
    def style_overrides(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class TexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main: Path
    markers: list[MarkerSpec] = Field(default_factory=lambda: [MarkerSpec(color="revcolor")])
    detect_macros: bool = True
    replacements: dict[str, str] = Field(default_factory=dict)
    include_captions: bool = True
    include_footnotes: bool = True
    min_segment_chars: int = Field(4, ge=1)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Optional[Path] = None
    output: Optional[Path] = None
    password: Optional[str] = None
    remove_existing: bool = True
    defaults: Style = Field(default_factory=Style)
    annotations: list[AnnotationSpec] = Field(default_factory=list)
    tex: Optional[TexConfig] = None  # entries generated from LaTeX every time the config is applied
    tex_source: Optional[TexConfig] = None  # LaTeX the entries above were generated from (for re-importing)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Config":
        path = Path(path)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"{path}: invalid YAML/JSON: {e}") from e
        if not isinstance(raw, dict):
            raise ConfigError(f"{path}: top level must be a mapping")
        try:
            cfg = cls.model_validate(raw)
        except ValidationError as e:
            raise ConfigError(f"{path}:\n{_format_errors(e)}") from e
        try:
            cfg.entries()  # surface per-entry style errors at load time
        except ConfigError as e:
            raise ConfigError(f"{path}: {e}") from e
        return cfg.resolve_paths(path.parent)

    def resolve_paths(self, base: Path) -> "Config":
        def fix(p: Optional[Path]) -> Optional[Path]:
            return p if p is None or p.is_absolute() else (base / p)

        self.input, self.output = fix(self.input), fix(self.output)
        for tex in (self.tex, self.tex_source):
            if tex is not None:
                tex.main = fix(tex.main)  # type: ignore[assignment]
        return self

    def entries(self) -> list["Entry"]:
        return [resolve_entry(spec, self.defaults, i) for i, spec in enumerate(self.annotations)]


@dataclass
class Entry:
    """An annotation entry with defaults applied."""

    index: int
    spec: AnnotationSpec
    style: Style

    @property
    def label(self) -> str:
        what = self.spec.text if self.spec.text is not None else f"/{self.spec.regex}/"
        preview = what if len(what) <= 60 else what[:57] + "..."
        return f"#{self.index + 1} {preview!r}" + (f" ({self.spec.source})" if self.spec.source else "")


def resolve_entry(spec: AnnotationSpec, defaults: Style, index: int) -> Entry:
    try:
        style = Style.model_validate({**defaults.model_dump(), **(spec.model_extra or {})})
    except ValidationError as e:
        raise ConfigError(f"annotation #{index + 1}:\n{_format_errors(e)}") from e
    return Entry(index=index, spec=spec, style=style)


def _format_errors(e: ValidationError) -> str:
    lines = []
    for err in e.errors():
        loc = ".".join(str(x + 1) if isinstance(x, int) else str(x) for x in err["loc"])
        lines.append(f"  - {loc or '(root)'}: {err['msg']}")
    return "\n".join(lines)


def dump_config(data: dict[str, Any], path: Union[str, Path]) -> None:
    """Write a config dict as YAML (or JSON for *.json)."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")


__all__ = [
    "AnnotationSpec",
    "Config",
    "ConfigError",
    "Entry",
    "MarkerSpec",
    "Style",
    "TexConfig",
    "dump_config",
    "pages_to_indices",
    "parse_pages",
    "resolve_entry",
    "to_hex",
]
