"""Command line interface: ``notepdf apply | tex | tex2config | list | clear | gui``."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import pymupdf

from .annotate import list_annots, remove_notepdf_annots
from .apply import apply, collect_entries
from .config import Config, ConfigError, MarkerSpec, TexConfig, dump_config
from .report import print_report, write_report_json


def main(argv: Optional[list[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, FileNotFoundError, RecursionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="notepdf", description="Add highlights and comments to PDFs from a config file or LaTeX markers.")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("apply", help="annotate a PDF as described by a YAML/JSON config")
    a.add_argument("config", type=Path)
    a.add_argument("-i", "--input", type=Path, help="input PDF (overrides 'input')")
    a.add_argument("-o", "--output", type=Path, help="output PDF (overrides 'output')")
    _run_flags(a)
    a.set_defaults(func=_cmd_apply)

    t = sub.add_parser("tex", help="highlight the marked parts of a LaTeX source in its compiled PDF")
    t.add_argument("main", type=Path, help="main .tex file")
    t.add_argument("pdf", type=Path, help="compiled PDF")
    t.add_argument("-o", "--output", type=Path, help="output PDF (default: <pdf>.annotated.pdf)")
    t.add_argument("--save-config", type=Path, help="also write the generated config here")
    _marker_flags(t)
    _run_flags(t)
    t.set_defaults(func=_cmd_tex)

    g = sub.add_parser("tex2config", help="write an editable config from the markers in a LaTeX source")
    g.add_argument("main", type=Path, help="main .tex file")
    g.add_argument("-o", "--output", type=Path, required=True, help="config file to write (.yaml or .json)")
    g.add_argument("--pdf", type=Path, help="PDF to put in the config's 'input'")
    _marker_flags(g)
    g.set_defaults(func=_cmd_tex2config)

    ls = sub.add_parser("list", help="list the annotations in a PDF")
    ls.add_argument("pdf", type=Path)
    ls.add_argument("--json", action="store_true", help="print JSON")
    ls.add_argument("--all", action="store_true", help="include annotations not made by NotePDF")
    ls.set_defaults(func=_cmd_list)

    c = sub.add_parser("clear", help="remove the annotations NotePDF added")
    c.add_argument("pdf", type=Path)
    c.add_argument("-o", "--output", type=Path, help="write here instead of updating the PDF in place")
    c.set_defaults(func=_cmd_clear)

    u = sub.add_parser("gui", help="open the graphical interface in your browser")
    u.add_argument("path", nargs="?", help="PDF, config or .tex file to open")
    u.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    u.add_argument("--port", type=int, default=8766, help="port (default 8766)")
    u.add_argument("--no-browser", action="store_true", help="don't open a browser")
    u.add_argument("--app", action="store_true", help=argparse.SUPPRESS)  # backend for the desktop app
    u.set_defaults(func=_cmd_gui)
    return p


def _run_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true", help="match and report, but don't write a PDF")
    p.add_argument("--strict", action="store_true", help="exit with status 1 if a required entry isn't found")
    p.add_argument("--report", type=Path, help="write a JSON report here")
    p.add_argument("-v", "--verbose", action="store_true", help="list every entry, not just problems")


def _marker_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("-c", "--config", type=Path, help="config with defaults and/or a 'tex' section (markers, replacements, ...)")
    p.add_argument("--color", action="append", default=[], metavar="NAME", help="TeX color marker, e.g. revcolor (repeatable)")
    p.add_argument("--macro", action="append", default=[], metavar="NAME", help="macro marker, e.g. rev for \\rev{...} (repeatable)")
    p.add_argument("--env", action="append", default=[], metavar="NAME", help="environment marker (repeatable)")
    p.add_argument("--highlight", metavar="COLOR", help="highlight color for --color/--macro/--env markers ('tex' = the TeX color)")


# -- commands ---------------------------------------------------------------------------------------


def _cmd_apply(args: argparse.Namespace) -> int:
    cfg = Config.load(args.config)
    report = apply(cfg, args.input, args.output, dry_run=args.dry_run)
    return _finish(report, args)


def _cmd_tex(args: argparse.Namespace) -> int:
    cfg = _tex_config(args)
    if args.save_config:
        _write_tex_config(cfg, args.pdf, args.save_config)
    entries, notes = collect_entries(cfg)
    report = apply(cfg, args.pdf, args.output, dry_run=args.dry_run, entries=entries)
    report.notes = notes
    return _finish(report, args)


def _cmd_tex2config(args: argparse.Namespace) -> int:
    cfg = _tex_config(args)
    result = _write_tex_config(cfg, args.pdf, args.output)
    for note in result.notes:
        print(f"[note] {note}")
    print(f"{len(result.rows)} entries from {len(result.markers)} marker(s) -> {args.output}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    with pymupdf.open(args.pdf) as doc:
        rows = list_annots(doc)
    if not args.all:
        rows = [r for r in rows if (r["id"] or "").startswith("notepdf-")]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    for r in rows:
        line = f"p{r['page']:<3} {r['type']:<10} {r['color'] or '-':<8} {r['text'] or ''!r}"
        if r["comment"]:
            line += f"  // {r['comment']}"
        print(line)
    print(f"{len(rows)} annotation(s)")
    return 0


def _cmd_clear(args: argparse.Namespace) -> int:
    with pymupdf.open(args.pdf) as doc:
        removed = remove_notepdf_annots(doc)
        if args.output and args.output.resolve() != args.pdf.resolve():
            doc.save(args.output, garbage=3, deflate=True)
        elif removed:
            doc.saveIncr()
    print(f"removed {removed} annotation(s)" + (f" -> {args.output}" if args.output else ""))
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from .gui import files
        from .gui.server import LOCAL_HOSTS, create_app
    except ImportError as e:
        print(f"error: the GUI needs extra packages ({e.name}): uv sync --extra gui", file=sys.stderr)
        return 2
    # Host-header checking only makes sense when bound to loopback.
    app = create_app(LOCAL_HOSTS if args.host in LOCAL_HOSTS else None, app_mode=args.app, initial=args.path)
    if args.app:
        _exit_with_parent()
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}"
    print(f"NotePDF at {url}  (Ctrl+C to stop)")
    if not (args.no_browser or args.app):
        threading.Timer(0.8, files.open_url, [url]).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _exit_with_parent() -> None:
    """The desktop app owns this process; don't outlive it if the app is killed or crashes."""
    parent = os.getppid()

    def watch() -> None:
        while os.getppid() == parent:
            time.sleep(2)
        os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


# -- helpers ----------------------------------------------------------------------------------------


def _tex_config(args: argparse.Namespace) -> Config:
    cfg = Config.load(args.config) if args.config else Config()
    flags = (
        [MarkerSpec(color=n, highlight=args.highlight) for n in args.color]
        + [MarkerSpec(macro=n, highlight=args.highlight) for n in args.macro]
        + [MarkerSpec(env=n, highlight=args.highlight) for n in args.env]
    )
    if cfg.tex is None:
        cfg.tex = TexConfig(main=args.main, markers=flags) if flags else TexConfig(main=args.main)
    else:
        cfg.tex.main = args.main
        if flags:
            cfg.tex.markers = flags
    return cfg


def _write_tex_config(cfg: Config, pdf: Optional[Path], out: Path):
    from .tex.to_config import tex_config_dict

    assert cfg.tex is not None
    data, result = tex_config_dict(cfg.tex, cfg, pdf, out)
    if cfg.annotations:
        data["annotations"] = [a.model_dump(exclude_none=True, exclude_defaults=True) for a in cfg.annotations] + data["annotations"]
    dump_config(data, out)
    if out.suffix.lower() != ".json":
        header = [f"# Generated by `notepdf tex2config` from {cfg.tex.main.name}. Edit freely, then run: notepdf apply {out.name}"]
        if result.notes:
            header.append("# Notes:")
            header += [f"#   {n}" for n in result.notes]
        out.write_text("\n".join(header) + "\n" + out.read_text(encoding="utf-8"), encoding="utf-8")
    return result


def _finish(report, args: argparse.Namespace) -> int:
    print_report(report, verbose=args.verbose)
    if args.report:
        write_report_json(report, args.report)
    return 1 if args.strict and report.missing_required else 0


if __name__ == "__main__":
    sys.exit(main())
