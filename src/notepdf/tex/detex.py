r"""Convert a marked LaTeX fragment into text segments that can be found in the PDF.

The output doesn't have to look like the PDF; it has to *match* it in ``normalized`` mode, which
compares letters and digits only. So:

* text-style commands keep their argument (``\emph{x}`` -> ``x``),
* things whose rendering can't be predicted become ``{{gap:N}}`` (citations, references, inline math),
* paragraphs, list items, headings, display math and floats split the fragment into segments,
  so one unmatched piece doesn't lose the rest,
* display math and float bodies are skipped and reported; captions and footnotes become their own
  segments (they appear elsewhere on the page).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Union

from ..messages import Msg
from ..textindex import loose_chars
from .scan import find_env_end, read_args, read_command, read_group, read_optional, skip_ws

MAX_GAP = 300
REF_GAP = 40
FOOTNOTE_MARK_GAP = 4
MAX_EXPANSION_DEPTH = 6

SECTIONS = {"part", "chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph"}
KEEP_ARG = {
    "emph", "textbf", "textit", "texttt", "textsc", "textrm", "textsf", "textup", "textsl", "textmd",
    "textnormal", "underline", "uline", "mbox", "makebox", "text", "hbox", "fbox", "framebox", "enquote",
    "textsuperscript", "textsubscript", "hyperref", "hl", "sout", "xout", "ul", "MakeUppercase",
    "MakeLowercase", "uppercase", "lowercase", "textls", "acrshort", "acrlong", "acrfull", "gls", "Gls",
}
KEEP_SECOND = {"textcolor", "colorbox", "href", "foreignlanguage"}
CITES = re.compile(r"(?:[a-zA-Z]*cite[a-zA-Z]*|nocite)\*?")
REFS = {"ref", "eqref", "autoref", "cref", "Cref", "pageref", "nameref", "vref", "Vref", "cpageref", "labelcref"}
GAP_ARG = {"url": 60, "nolinkurl": 60, "doi": 40, "SI": 20, "si": 10, "qty": 20, "unit": 10, "ang": 10}
DROP = {  # name -> number of mandatory args to swallow
    "label": 1, "index": 1, "glossary": 1, "vspace": 1, "hspace": 1, "addvspace": 1, "phantom": 1,
    "hphantom": 1, "vphantom": 1, "includegraphics": 1, "bibliographystyle": 1, "bibliography": 1,
    "setlength": 2, "addtolength": 2, "setcounter": 2, "addtocounter": 2, "addcontentsline": 3,
    "color": 1, "pagecolor": 1, "linespread": 1, "fontsize": 2, "selectfont": 0, "thispagestyle": 1,
    "pagestyle": 1, "newpage": 0, "clearpage": 0, "cleardoublepage": 0, "noindent": 0, "indent": 0,
    "centering": 0, "raggedright": 0, "raggedleft": 0, "small": 0, "footnotesize": 0, "scriptsize": 0,
    "tiny": 0, "large": 0, "Large": 0, "LARGE": 0, "huge": 0, "Huge": 0, "normalsize": 0, "bfseries": 0,
    "itshape": 0, "ttfamily": 0, "scshape": 0, "rmfamily": 0, "sffamily": 0, "upshape": 0, "mdseries": 0,
    "slshape": 0, "normalfont": 0, "em": 0, "bf": 0, "it": 0, "rm": 0, "tt": 0, "sc": 0, "sf": 0,
    "protect": 0, "relax": 0, "xspace": 0, "ignorespaces": 0, "unskip": 0, "hfill": 0, "vfill": 0,
    "smallskip": 0, "medskip": 0, "bigskip": 0, "nobreak": 0, "allowbreak": 0, "linebreak": 0,
    "pagebreak": 0, "noalign": 0, "maketitle": 0, "tableofcontents": 0, "normalcolor": 0, "leavevmode": 0,
    "nopagebreak": 0, "vskip": 0, "hskip": 0, "footnotemark": 0, "strut": 0, "displaystyle": 0,
}
SYMBOLS = {
    "ldots": "...", "dots": "...", "textellipsis": "...", "textendash": "-", "textemdash": "-",
    "LaTeX": "LaTeX", "TeX": "TeX", "LaTeXe": "LaTeX2e", "S": "§", "P": "¶", "copyright": "©",
    "textregistered": "®", "texttrademark": "™", "ss": "ß", "o": "ø", "O": "Ø", "l": "ł", "L": "Ł",
    "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ", "aa": "å", "AA": "Å", "i": "i", "j": "j",
    "textasciitilde": "~", "textbackslash": "\\", "textbar": "|", "textless": "<", "textgreater": ">",
    "textdegree": "°", "textpercent": "%", "newline": " ", "quad": " ", "qquad": " ", "enspace": " ",
    "thinspace": " ", "nobreakspace": " ", "textquotedblleft": '"', "textquotedblright": '"',
    "textquoteleft": "'", "textquoteright": "'", "slash": "/", "textasteriskcentered": "*",
    "dag": "†", "ddag": "‡", "textdagger": "†", "pounds": "£", "euro": "€", "checkmark": "✓",
}
ACCENTS = set("'`^\"~=.")
LETTER_ACCENTS = {"c", "d", "b", "H", "k", "r", "u", "v", "t"}
DISPLAY_MATH = {"equation", "align", "gather", "multline", "eqnarray", "displaymath", "flalign", "alignat"}
FLOATS = {"figure", "table", "algorithm", "wrapfigure", "wraptable", "sidewaysfigure", "sidewaystable", "subfigure", "subtable", "SCfigure", "listing"}
SKIP_ENVS = {"tabular", "tabularx", "tabular*", "longtable", "tikzpicture", "verbatim", "Verbatim", "lstlisting", "minted", "algorithmic", "picture", "pgfpicture", "forest", "comment"}
LISTS = {"itemize", "enumerate", "description", "compactitem", "compactenum", "inparaenum"}
ENV_ARGS = {"minipage": 1, "multicols": 1, "adjustbox": 1, "wrapfigure": 2, "wraptable": 2, "subfigure": 1, "subtable": 1, "tabularx": 2, "tabular": 1, "tcolorbox": 0, "otherlanguage": 1}


@dataclass
class Segment:
    text: str  # literal text with {{gap:N}} placeholders
    kind: str  # "text" | "heading" | "caption" | "footnote"
    pos: int  # source position (in TexSource.text) where the segment starts


@dataclass
class DetexResult:
    segments: list[Segment] = field(default_factory=list)
    skipped: list[tuple[int, Msg]] = field(default_factory=list)  # (source position, what was skipped)


class _Builder:
    def __init__(self, kind: str = "text"):
        self.kind = kind
        self.parts: list[Union[str, int]] = []
        self.pos: Optional[int] = None
        self.segments: list[Segment] = []

    def text(self, t: str, pos: int) -> None:
        if not t:
            return
        if self.pos is None:
            if not t.strip():
                return
            self.pos = pos
        self.parts.append(t)

    def gap(self, n: int, pos: int) -> None:
        if self.pos is None:
            self.pos = pos
        self.parts.append(n)

    def brk(self) -> None:
        merged: list[Union[str, int]] = []
        for p in self.parts:
            if merged and type(merged[-1]) is type(p):
                merged[-1] = merged[-1] + p  # type: ignore[operator]
            else:
                merged.append(p)
        # Edge gaps stay: the matcher uses them to extend over e.g. a trailing reference number.
        while merged and isinstance(merged[0], str) and not merged[0].strip():
            merged.pop(0)
        while merged and isinstance(merged[-1], str) and not merged[-1].strip():
            merged.pop()
        out = "".join(re.sub(r"\s+", " ", p) if isinstance(p, str) else f"{{{{gap:{min(p, MAX_GAP)}}}}}" for p in merged).strip()
        if out and self.pos is not None:
            self.segments.append(Segment(out, self.kind, self.pos))
        self.parts, self.pos = [], None


class Detexer:
    def __init__(
        self,
        text_macros: Optional[dict[str, str]] = None,
        replacements: Optional[dict[str, str]] = None,
        include_captions: bool = True,
        include_footnotes: bool = True,
    ):
        self.expansions: dict[str, str] = dict(text_macros or {})
        for k, v in (replacements or {}).items():
            self.expansions[k.lstrip("\\")] = v
        self.include_captions = include_captions
        self.include_footnotes = include_footnotes

    def run(self, s: str, start: int, end: int) -> DetexResult:
        self.result = DetexResult()
        self.sides: list[Segment] = []
        out = _Builder()
        self._walk(s, start, end, out, None, 0)
        out.brk()
        self.result.segments = sorted(out.segments + self.sides, key=lambda seg: seg.pos)
        return self.result

    # -- walker ------------------------------------------------------------------------------------

    def _walk(self, s: str, i: int, end: int, out: _Builder, base: Optional[int], depth: int) -> None:
        def at(k: int) -> int:
            return k if base is None else base

        while i < end:
            c = s[i]
            if c == "\\":
                i = self._command(s, i, end, out, base, depth)
            elif c == "$":
                if s.startswith("$$", i):
                    close = s.find("$$", i + 2, end)
                    close = end if close < 0 else close + 2
                    self._skip(out, at(i), Msg("skip_display_math", "display math ($$) is not highlighted", env="$$"))
                    i = close
                else:
                    close = _find_unescaped(s, "$", i + 1, end)
                    out.gap(_math_gap(close - i - 1), at(i))
                    i = close + 1
            elif c in "{}":
                i += 1
            elif c == "~":
                out.text(" ", at(i))
                i += 1
            elif c == "\n":
                j = i + 1
                while j < end and s[j] in " \t":
                    j += 1
                if j < end and s[j] == "\n":  # blank line = paragraph break
                    out.brk()
                    i = skip_ws(s, j)
                else:
                    out.text(" ", at(i))
                    i += 1
            elif c == "-":
                j = i
                while j < end and s[j] == "-":
                    j += 1
                out.text("-", at(i))
                i = j
            elif c == "`" or (c == "'" and s.startswith("''", i)):
                n = 2 if s.startswith(c * 2, i) else 1
                out.text('"' if n == 2 else "'", at(i))
                i += n
            elif c == "&":
                out.text(" ", at(i))
                i += 1
            else:
                out.text(c, at(i))
                i += 1

    def _command(self, s: str, i: int, end: int, out: _Builder, base: Optional[int], depth: int) -> int:
        pos = i if base is None else base
        cmd = read_command(s, i)
        if cmd is None:
            return i + 1
        name, e = cmd
        e = min(e, end)
        bare = name.rstrip("*") or name

        # control symbols
        if len(name) == 1 and not name.isalpha():
            if name in "%&_#${}":
                out.text(name, pos)
            elif name == "\\":
                if e < end and s[e] == "*":
                    e += 1
                opt = read_optional(s, skip_ws(s, e))
                out.text(" ", pos)
                return opt[1] + 1 if opt else e
            elif name in ",;:! \n\t":
                out.text(" ", pos)
            elif name in ACCENTS:
                return self._accent(s, e, end, out, pos)
            elif name == "[":
                close = s.find("\\]", e, end)
                self._skip(out, pos, Msg("skip_display_math", "display math (\\[...\\]) is not highlighted", env="\\[...\\]"))
                return end if close < 0 else close + 2
            elif name == "(":
                close = s.find("\\)", e, end)
                close = end if close < 0 else close
                out.gap(_math_gap(close - e), pos)
                return close + 2
            return e

        if bare == "begin":
            grp = read_group(s, skip_ws(s, e))
            if grp is None:
                return e
            return self._env(s, s[grp[0] : grp[1]].strip(), grp[1] + 1, end, out, base, depth)
        if bare == "end":
            grp = read_group(s, skip_ws(s, e))
            out.brk()
            return grp[1] + 1 if grp else e
        if bare in SECTIONS:
            args, k = read_args(s, e, 1)
            out.brk()
            if args:
                hb = _Builder("heading")
                self._walk(s, args[0][0], args[0][1], hb, base, depth)
                hb.brk()
                out.segments.extend(hb.segments)
            return k
        if bare in ("footnote", "footnotetext"):
            args, k = read_args(s, e, 1)
            out.gap(FOOTNOTE_MARK_GAP, pos)
            if args and self.include_footnotes:
                self._side("footnote", s, args[0], base, depth)
            return k
        if bare in ("caption", "subcaption", "captionof"):
            args, k = read_args(s, e, 2 if bare == "captionof" else 1)
            if args and self.include_captions:
                self._side("caption", s, args[-1], base, depth)
            return k
        if bare == "item":
            j = skip_ws(s, e)
            opt = read_optional(s, j)
            out.brk()
            if opt:
                self._walk(s, opt[0], opt[1], out, base, depth)
                out.text(" ", pos)
                return opt[1] + 1
            return e
        if bare == "par":
            out.brk()
            return e
        if bare in KEEP_ARG:
            args, k = read_args(s, e, 1)
            if args:
                self._walk(s, args[0][0], args[0][1], out, base, depth)
            return k
        if bare in KEEP_SECOND:
            args, k = read_args(s, e, 2)
            if len(args) == 2:
                self._walk(s, args[1][0], args[1][1], out, base, depth)
            return k
        if CITES.fullmatch(name):
            args, k = read_args(s, e, 1)
            keys = s[args[0][0] : args[0][1]].count(",") + 1 if args else 1
            out.gap(min(30 * keys + 20, MAX_GAP), pos)
            return k
        if bare in REFS:
            args, k = read_args(s, e, 1)
            out.gap(REF_GAP, pos)
            return k
        if bare in GAP_ARG:
            n = 2 if bare in ("SI", "qty") else 1
            args, k = read_args(s, e, n)
            out.gap(GAP_ARG[bare], pos)
            return k
        if bare in DROP:
            if DROP[bare] == 0:
                return e
            _, k = read_args(s, e, DROP[bare])
            return k
        if name in LETTER_ACCENTS:
            return self._accent(s, e, end, out, pos)
        if bare in SYMBOLS:
            out.text(SYMBOLS[bare], pos)
            return _eat_empty_group(s, e, end)
        if bare in self.expansions and depth < MAX_EXPANSION_DEPTH:
            body = self.expansions[bare]
            self._walk(body, 0, len(body), out, pos, depth + 1)
            return _eat_empty_group(s, e, end)

        # Unknown command: one braced argument is probably text; several are probably not.
        groups: list[tuple[int, int]] = []
        k = e
        while True:
            j = k
            opt = read_optional(s, j)
            if opt:
                k = opt[1] + 1
                continue
            grp = read_group(s, j)
            if grp is None or grp[1] >= end:
                break
            groups.append(grp)
            k = grp[1] + 1
        if len(groups) == 1:
            self._walk(s, groups[0][0], groups[0][1], out, base, depth)
        elif len(groups) > 1:
            out.gap(min(sum(b - a for a, b in groups) + 6, MAX_GAP), pos)
        return k

    def _accent(self, s: str, e: int, end: int, out: _Builder, pos: int) -> int:
        j = skip_ws(s, e)
        grp = read_group(s, j)
        if grp is not None:
            inner = _Builder()
            self._walk(s, grp[0], grp[1], inner, pos, 0)
            out.text("".join(p for p in inner.parts if isinstance(p, str)), pos)
            return grp[1] + 1
        if j < end and s[j] == "\\":
            cmd = read_command(s, j)
            if cmd and cmd[0] in SYMBOLS:
                out.text(SYMBOLS[cmd[0]], pos)
                return cmd[1]
        if j < end:
            out.text(s[j], pos)
            return j + 1
        return j

    def _env(self, s: str, env: str, i: int, end: int, out: _Builder, base: Optional[int], depth: int) -> int:
        pos = i if base is None else base
        bare = env.rstrip("*")
        end_start, after = find_env_end(s, i, env)
        end_start, after = min(end_start, end), min(after, end)
        if bare == "math":
            out.gap(_math_gap(end_start - i), pos)
            return after
        out.brk()
        if bare in DISPLAY_MATH or env in DISPLAY_MATH:
            self._skip(out, pos, Msg("skip_display_math", f"display math ({env}) is not highlighted", env=env))
            return after
        if bare in FLOATS:
            found = False
            for m in re.finditer(r"\\(?:sub)?caption\*?", s[i:end_start]):
                if not self.include_captions:
                    break
                args, _ = read_args(s, i + m.end(), 1)
                if args:
                    self._side("caption", s, args[0], base, depth)
                    found = True
            text = f"{env} contents are not highlighted" + (" (its caption is)" if found else "")
            self._skip(out, pos, Msg("skip_float_caption" if found else "skip_float", text, env=env))
            return after
        if bare in SKIP_ENVS or env in SKIP_ENVS:
            self._skip(out, pos, Msg("skip_env", f"{env} environment is not highlighted", env=env))
            return after
        k = i
        n_args = ENV_ARGS.get(env, ENV_ARGS.get(bare, 0))
        _, k = read_args(s, k, n_args)
        self._walk(s, k, end_start, out, base, depth)
        out.brk()
        return after

    def _side(self, kind: str, s: str, span: tuple[int, int], base: Optional[int], depth: int) -> None:
        b = _Builder(kind)
        self._walk(s, span[0], span[1], b, base, depth)
        b.brk()
        self.sides.extend(b.segments)

    def _skip(self, out: _Builder, pos: int, what: Msg) -> None:
        out.brk()
        self.result.skipped.append((pos, what))


def _math_gap(source_len: int) -> int:
    return min(max(source_len, 1) + 6, 200)


def _find_unescaped(s: str, ch: str, i: int, end: int) -> int:
    while i < end:
        k = s.find(ch, i, end)
        if k < 0:
            return end
        backslashes = 0
        j = k - 1
        while j >= 0 and s[j] == "\\":
            backslashes += 1
            j -= 1
        if backslashes % 2 == 0:
            return k
        i = k + 1
    return end


def _eat_empty_group(s: str, e: int, end: int) -> int:
    return e + 2 if s.startswith("{}", e) and e + 2 <= end else e


def literal_length(segment_text: str) -> int:
    """Number of letters/digits outside gap placeholders."""
    return len(loose_chars(re.sub(r"\{\{\s*gap[^}]*\}\}", "", segment_text)))
