"""Human-readable and JSON summaries of an apply run."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, TextIO

from .apply import Report
from .colors import to_hex

_MARK = {"found": "ok  ", "warning": "warn", "missing": "MISS"}


def print_report(report: Report, out: Optional[TextIO] = None, verbose: bool = False) -> None:
    out = out or sys.stdout
    for res in report.results:
        if res.status == "found" and not verbose:
            continue
        pages = ",".join(map(str, res.pages)) or "-"
        mark = "opt " if res.status == "missing" and not res.entry.spec.required else _MARK[res.status]
        print(f"[{mark}] {res.entry.label}  pages: {pages}", file=out)
        for w in res.warnings:
            print(f"         {w}", file=out)
    for note in report.notes:
        print(f"[note] {note}", file=out)

    total = len(report.results)
    found = sum(1 for r in report.results if r.spans)
    annots = sum(len(r.placed) for r in report.results)
    line = f"{found}/{total} entries matched, {annots} annotation(s)"
    if report.removed:
        line += f", {report.removed} previous NotePDF annotation(s) replaced"
    if report.dry_run:
        line += " (dry run, nothing saved)"
    elif report.output:
        line += f" -> {report.output}"
    print(line, file=out)


def report_dict(report: Report) -> dict:
    return {
        "input": str(report.input),
        "output": str(report.output) if report.output else None,
        "removed": report.removed,
        "notes": report.notes,
        "entries": [
            {
                "index": r.entry.index + 1,
                "status": r.status,
                "text": r.entry.spec.text,
                "regex": r.entry.spec.regex,
                "source": r.entry.spec.source,
                "group": r.entry.spec.group,
                "color": to_hex(r.entry.style.color),
                "pages": r.pages,
                "match_modes": sorted({s.mode for s in r.spans}),
                "scores": [round(s.score, 1) for s in r.spans],
                "text_color_share": [None if s.color_share is None else round(s.color_share, 2) for s in r.spans],
                "warnings": r.warnings,
            }
            for r in report.results
        ],
    }


def write_report_json(report: Report, path: Path) -> None:
    path.write_text(json.dumps(report_dict(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
