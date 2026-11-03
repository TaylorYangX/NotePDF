r"""Load a LaTeX project into one comment-free string, keeping a map back to file:line.

* ``\input``/``\include``/``\subfile`` are inlined recursively.
* ``%`` comments are removed the way TeX does: the comment *and the line break* disappear, so
  ``foo%\nbar`` reads as ``foobar``. Leading spaces of every line are dropped too.
* ``%@note: ...`` comments are kept as positioned notes; they become annotation comments.
* ``\begin{comment}...\end{comment}`` and ``\iffalse...\fi`` are blanked out (length preserved).
* The preamble provides ``\definecolor`` values, zero-argument text macros, and macros that wrap a
  marker color (``\newcommand{\rev}[1]{{\color{revcolor}#1}}``).
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..colors import RGB

NOTE_RE = re.compile(r"^\s*@note\b\s*:?\s?(.*)$", re.IGNORECASE)
INPUT_RE = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]+)\}")
MAX_DEPTH = 20

XCOLOR_BASE: dict[str, RGB] = {
    "red": (1, 0, 0), "green": (0, 1, 0), "blue": (0, 0, 1), "cyan": (0, 1, 1), "magenta": (1, 0, 1),
    "yellow": (1, 1, 0), "black": (0, 0, 0), "white": (1, 1, 1), "gray": (0.5, 0.5, 0.5),
    "darkgray": (0.25, 0.25, 0.25), "lightgray": (0.75, 0.75, 0.75), "brown": (0.75, 0.5, 0.25),
    "lime": (0.75, 1, 0), "olive": (0.5, 0.5, 0), "orange": (1, 0.5, 0), "pink": (1, 0.75, 0.75),
    "purple": (0.75, 0, 0.25), "teal": (0, 0.5, 0.5), "violet": (0.5, 0, 0.5),
}


@dataclass
class Note:
    pos: int
    text: str


@dataclass
class MacroDef:
    name: str
    nargs: int
    has_optional: bool
    body: str


@dataclass
class TexSource:
    text: str
    body_start: int
    body_end: int
    notes: list[Note] = field(default_factory=list)
    colors: dict[str, RGB] = field(default_factory=dict)
    macros: dict[str, MacroDef] = field(default_factory=dict)
    root: Path = Path(".")
    _map_pos: list[int] = field(default_factory=list)
    _map_loc: list[tuple[Path, int]] = field(default_factory=list)

    def locate(self, pos: int) -> tuple[Path, int]:
        """File and 1-based line of a position in ``text``."""
        k = bisect.bisect_right(self._map_pos, pos) - 1
        if k < 0:
            return (self.root, 1)
        path, line = self._map_loc[k]
        return path, line

    def source_ref(self, pos: int) -> str:
        path, line = self.locate(pos)
        try:
            shown = path.relative_to(self.root)
        except ValueError:
            shown = path
        return f"{shown}:{line}"

    @property
    def text_macros(self) -> dict[str, str]:
        return {name: m.body for name, m in self.macros.items() if m.nargs == 0 and "#" not in m.body}


def read_tex(main: Path) -> TexSource:
    main = Path(main)
    if not main.is_file():
        raise FileNotFoundError(f"TeX file not found: {main}")
    out: list[str] = []
    src = TexSource(text="", body_start=0, body_end=0, root=main.parent.resolve())
    length = [0]
    _flatten(main.resolve(), out, src, length, depth=0)
    text = _blank_ignored("".join(out))
    src.text = text

    begin = re.search(r"\\begin\s*\{document\}", text)
    end = re.search(r"\\end\s*\{document\}", text)
    src.body_start = begin.end() if begin else 0
    src.body_end = end.start() if end and end.start() >= src.body_start else len(text)
    preamble = text[: begin.start()] if begin else ""
    src.colors = parse_colors(preamble)
    src.macros = parse_macros(preamble)
    return src


def _flatten(path: Path, out: list[str], src: TexSource, length: list[int], depth: int) -> None:
    if depth > MAX_DEPTH:
        raise RecursionError(f"\\input nesting deeper than {MAX_DEPTH} at {path}")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    def emit(s: str, lineno: int) -> None:
        if not s:
            return
        src._map_pos.append(length[0])
        src._map_loc.append((path, lineno))
        out.append(s)
        length[0] += len(s)

    for lineno, line in enumerate(lines, start=1):
        line = line.lstrip(" \t")
        cut = _comment_start(line)
        note = None
        if cut is not None:
            m = NOTE_RE.match(line[cut + 1 :])
            note = m.group(1).strip() if m and m.group(1).strip() else None
            content, newline = line[:cut], ""
        else:
            content, newline = line, "\n"

        pos = 0
        for m in INPUT_RE.finditer(content):
            emit(content[pos : m.start()], lineno)
            child = _resolve_input(path.parent, m.group(1).strip(), src.root)
            if child is not None:
                _flatten(child, out, src, length, depth + 1)
            pos = m.end()
        emit(content[pos:], lineno)
        if note:
            src.notes.append(Note(length[0], note))
        emit(newline, lineno)


def _comment_start(line: str) -> Optional[int]:
    i = 0
    while True:
        i = line.find("%", i)
        if i < 0:
            return None
        backslashes = 0
        j = i - 1
        while j >= 0 and line[j] == "\\":
            backslashes += 1
            j -= 1
        if backslashes % 2 == 0:
            return i
        i += 1


def _resolve_input(base: Path, name: str, root: Path) -> Optional[Path]:
    for folder in (base, root):
        for cand in (folder / name, folder / f"{name}.tex"):
            if cand.is_file():
                return cand.resolve()
    return None


def _blank_ignored(text: str) -> str:
    """Replace ``comment`` environments and ``\\iffalse..\\fi`` with spaces, keeping newlines and length."""
    chars = list(text)

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if chars[k] != "\n":
                chars[k] = " "

    for m in re.finditer(r"\\begin\s*\{comment\}.*?\\end\s*\{comment\}", text, re.S):
        blank(m.start(), m.end())
    for m in re.finditer(r"\\iffalse(?![a-zA-Z@])", text):
        depth, k = 1, m.end()
        for t in re.finditer(r"\\(if[a-zA-Z@]*|fi)(?![a-zA-Z@])", text[k:]):
            depth += 1 if t.group(1) != "fi" else -1
            if depth == 0:
                blank(m.start(), k + t.end())
                break
    return "".join(chars)


# -- preamble ---------------------------------------------------------------------------------------

DEFINECOLOR_RE = re.compile(r"\\definecolor\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}")
COLORLET_RE = re.compile(r"\\colorlet\s*\{([^}]*)\}\s*\{([^}]*)\}")


def parse_colors(preamble: str) -> dict[str, RGB]:
    colors: dict[str, RGB] = dict(XCOLOR_BASE)
    for m in DEFINECOLOR_RE.finditer(preamble):
        rgb = _color_from_model(m.group(2).strip(), m.group(3).strip())
        if rgb is not None:
            colors[m.group(1).strip()] = rgb
    for m in COLORLET_RE.finditer(preamble):
        other = m.group(2).strip()
        if other in colors:
            colors[m.group(1).strip()] = colors[other]
    return colors


def _color_from_model(model: str, spec: str) -> Optional[RGB]:
    try:
        nums = [float(x) for x in re.split(r"[,\s]+", spec) if x] if model.lower() != "html" else []
        if model == "rgb" and len(nums) == 3:
            return (nums[0], nums[1], nums[2])
        if model == "RGB" and len(nums) == 3:
            return (nums[0] / 255, nums[1] / 255, nums[2] / 255)
        if model.lower() == "html" and len(spec) == 6:
            return tuple(int(spec[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]
        if model.lower() == "gray" and len(nums) == 1:
            return (nums[0], nums[0], nums[0])
        if model == "cmyk" and len(nums) == 4:
            c, m_, y, k = nums
            return ((1 - c) * (1 - k), (1 - m_) * (1 - k), (1 - y) * (1 - k))
    except ValueError:
        return None
    return None


NEWCOMMAND_RE = re.compile(
    r"\\(?:re|provide)?newcommand\*?\s*(?:\{\s*\\([a-zA-Z@]+)\s*\}|\\([a-zA-Z@]+))"
    r"\s*(?:\[(\d)\])?\s*(\[[^\]]*\])?\s*\{"
    r"|\\DeclareRobustCommand\*?\s*(?:\{\s*\\([a-zA-Z@]+)\s*\}|\\([a-zA-Z@]+))\s*(?:\[(\d)\])?\s*(\[[^\]]*\])?\s*\{"
)
DEF_RE = re.compile(r"\\(?:g|e|x)?def\s*\\([a-zA-Z@]+)\s*((?:#\d)*)\s*\{")


def parse_macros(preamble: str) -> dict[str, MacroDef]:
    from .scan import read_group  # local import: scan depends on nothing here

    macros: dict[str, MacroDef] = {}
    for m in NEWCOMMAND_RE.finditer(preamble):
        name = m.group(1) or m.group(2) or m.group(5) or m.group(6)
        nargs = int(m.group(3) or m.group(7) or 0)
        has_opt = bool(m.group(4) or m.group(8))
        grp = read_group(preamble, m.end() - 1)
        if grp:
            macros[name] = MacroDef(name, nargs, has_opt, preamble[grp[0] : grp[1]])
    for m in DEF_RE.finditer(preamble):
        grp = read_group(preamble, m.end() - 1)
        if grp:
            macros[m.group(1)] = MacroDef(m.group(1), m.group(2).count("#"), False, preamble[grp[0] : grp[1]])
    return macros
