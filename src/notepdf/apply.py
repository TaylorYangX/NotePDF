"""Run a config against a PDF: match every entry, write the annotations, save."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pymupdf

from .annotate import Placed, add_markup, remove_notepdf_annots, span_quads
from .config import Config, ConfigError, Entry, Style, resolve_entry
from .matcher import Matcher, Span
from .textindex import DocText


@dataclass
class EntryResult:
    entry: Entry
    spans: list[Span] = field(default_factory=list)
    placed: list[Placed] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.spans:
            return "missing"
        return "warning" if self.warnings else "found"

    @property
    def pages(self) -> list[int]:
        return sorted({p.page + 1 for p in self.placed})


@dataclass
class Report:
    input: Path
    output: Optional[Path]
    results: list[EntryResult] = field(default_factory=list)
    removed: int = 0
    notes: list[str] = field(default_factory=list)  # e.g. TeX content that was skipped
    dry_run: bool = False

    @property
    def missing(self) -> list[EntryResult]:
        return [r for r in self.results if r.status == "missing"]

    @property
    def missing_required(self) -> list[EntryResult]:
        return [r for r in self.missing if r.entry.spec.required]


def default_output(input_pdf: Path) -> Path:
    return input_pdf.with_name(f"{input_pdf.stem}.annotated.pdf")


def collect_entries(cfg: Config) -> tuple[list[Entry], list[str]]:
    """Manual entries followed by entries generated from ``cfg.tex``."""
    entries = cfg.entries()
    notes: list[str] = []
    if cfg.tex is not None:
        from .tex.to_config import tex_entries

        tex = tex_entries(cfg.tex)
        notes.extend(tex.notes)
        tex_defaults = tex_style_defaults(cfg.defaults, tex.default_overrides)
        start = len(entries)
        entries += [resolve_entry(spec, tex_defaults, start + i) for i, spec in enumerate(tex.specs)]
    return entries, notes


def tex_style_defaults(defaults: Style, overrides: dict) -> Style:
    """TeX entries default to sequential + fuzzy fallback unless the user set those keys explicitly."""
    update = {k: v for k, v in overrides.items() if k not in defaults.model_fields_set}
    return defaults.model_copy(update=update)


def apply(
    cfg: Config,
    input_pdf: Optional[Path] = None,
    output_pdf: Optional[Path] = None,
    dry_run: bool = False,
    entries: Optional[list[Entry]] = None,
) -> Report:
    input_pdf = Path(input_pdf or cfg.input or "")
    if not input_pdf.name:
        raise ConfigError("no input PDF: set 'input' in the config or pass -i")
    if not input_pdf.is_file():
        raise ConfigError(f"input PDF not found: {input_pdf}")
    output_pdf = Path(output_pdf or cfg.output or default_output(input_pdf))

    notes: list[str] = []
    if entries is None:
        entries, notes = collect_entries(cfg)

    doc = pymupdf.open(input_pdf)
    try:
        if doc.needs_pass and not doc.authenticate(cfg.password or ""):
            raise ConfigError(f"{input_pdf} is encrypted; set 'password' in the config")
        report = Report(input=input_pdf, output=None if dry_run else output_pdf, notes=notes, dry_run=dry_run)
        if cfg.remove_existing:
            report.removed = remove_notepdf_annots(doc)

        doctext = DocText.from_pdf(doc)
        report.results = match_entries(Matcher(doctext, doc.page_count), entries)
        group_comments = group_comment_map(entries)
        placed_groups: set[str] = set()
        for res in report.results:
            _place(doc, doctext, res, group_comments, placed_groups)

        if not dry_run:
            _save(doc, input_pdf, output_pdf)
        return report
    finally:
        doc.close()


def match_entries(matcher: Matcher, entries: list[Entry]) -> list[EntryResult]:
    """Find every entry, in order; sequential entries search forward from the previous match."""
    results = []
    cursor: Optional[int] = None
    for entry in entries:
        found = matcher.find(entry, cursor)
        if entry.style.sequential and found.spans:
            cursor = found.spans[-1].end
        results.append(EntryResult(entry, spans=found.spans, warnings=found.warnings))
    return results


def group_comment_map(entries: list[Entry]) -> dict[str, str]:
    """A group's comment goes on whichever of its annotations is placed first."""
    comments: dict[str, str] = {}
    for e in entries:
        if e.spec.group and e.spec.comment:
            comments.setdefault(e.spec.group, e.spec.comment)
    return comments


def _place(
    doc: pymupdf.Document,
    doctext: DocText,
    res: EntryResult,
    group_comments: dict[str, str],
    placed_groups: set[str],
) -> None:
    spec, style = res.entry.spec, res.entry.style
    group = spec.group
    comment = spec.comment or (group_comments.get(group) if group else None)
    seed_text = spec.text if spec.text is not None else spec.regex
    for span in res.spans:
        first = True
        for page_no, quads in sorted(span_quads(doctext, span).items()):
            if group:
                first = group not in placed_groups
                placed_groups.add(group)
            text = comment if first else _continuation(comment, style)
            seed = f"{res.entry.index}|{seed_text}|{span.start}|{page_no}"
            res.placed.append(add_markup(doc, page_no, quads, style, text, seed))
            first = False


def _continuation(comment: Optional[str], style: Style) -> Optional[str]:
    if not comment or style.continuation_comment == "none":
        return None
    return comment if style.continuation_comment == "same" else style.continuation_comment


def _save(doc: pymupdf.Document, input_pdf: Path, output_pdf: Path) -> None:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    if output_pdf.resolve() != input_pdf.resolve():
        doc.save(output_pdf, garbage=3, deflate=True)
    elif doc.can_save_incrementally():
        doc.saveIncr()
    else:  # e.g. repaired file: write a full copy next to it, then swap
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=output_pdf.parent)
        os.close(fd)
        doc.save(tmp, garbage=3, deflate=True)
        os.replace(tmp, output_pdf)
