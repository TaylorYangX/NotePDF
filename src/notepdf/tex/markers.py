r"""Find marked regions in the document body.

Supported markers (each configured by a ``MarkerSpec``):

* ``{\color{revcolor} ...}``: the color stays on until the enclosing group closes. That is a
  ``}``, ``\endgroup``, or the ``\end{..}`` of an environment opened before it, or until another
  ``\color``/``\normalcolor`` at the same level.
* ``\textcolor{revcolor}{...}``
* ``\rev{...}`` / ``\rev[opt]{...}``: macro markers, configured or auto-detected from
  ``\newcommand{\rev}[1]{{\color{revcolor}#1}}`` in the preamble.
* ``\begin{revised} ... \end{revised}``: environment markers.

A marker nested in another marker is part of the outer one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..colors import RGB
from ..config import MarkerSpec
from .reader import TexSource
from .scan import find_env_end, read_args, read_command, read_group, read_optional, skip_ws


@dataclass
class Marker:
    kind: str  # "color" | "textcolor" | "macro" | "env"
    name: str
    spec: MarkerSpec
    start: int  # outer extent, including a "{" that opens the color group
    end: int
    body_start: int
    body_end: int
    spec_index: int = 0
    tex_color: Optional[RGB] = None
    note: Optional[str] = None
    order: int = 0


def effective_specs(src: TexSource, specs: list[MarkerSpec], detect_macros: bool) -> tuple[list[MarkerSpec], dict[int, str]]:
    """Configured specs plus auto-detected wrapper macros. Also maps spec position -> TeX color name."""
    out = list(specs)
    color_of: dict[int, str] = {i: s.color for i, s in enumerate(out) if s.color}
    for i, s in enumerate(out):  # a configured macro marker takes its color from its definition
        if s.macro and s.macro in src.macros and (c := _wrapped_color(src.macros[s.macro].body)):
            color_of[i] = c
    if not detect_macros:
        return out, color_of
    known_macros = {s.macro for s in out if s.macro}
    color_specs = {s.color: s for s in out if s.color}
    for macro in src.macros.values():
        mandatory = macro.nargs - (1 if macro.has_optional else 0)
        if mandatory != 1 or macro.name in known_macros:
            continue
        wrapped = _wrapped_color(macro.body)
        if wrapped in color_specs:
            base = color_specs[wrapped]
            derived = MarkerSpec(macro=macro.name, highlight=base.highlight, comment=base.comment, **base.style_overrides)
            color_of[len(out)] = base.color  # type: ignore[assignment]
            out.append(derived)
            known_macros.add(macro.name)
    return out, color_of


def _wrapped_color(body: str) -> Optional[str]:
    m = re.search(r"\\(?:text)?color\s*\{([^}]*)\}", body)
    return m.group(1).strip() if m else None


def find_markers(src: TexSource, specs: list[MarkerSpec], detect_macros: bool = True) -> list[Marker]:
    specs, color_of = effective_specs(src, specs, detect_macros)
    by_color = {s.color: i for i, s in enumerate(specs) if s.color}
    by_macro = {s.macro: i for i, s in enumerate(specs) if s.macro}
    by_env = {s.env: i for i, s in enumerate(specs) if s.env}

    alts = []
    if by_color:
        names = "|".join(re.escape(n) for n in by_color)
        alts.append(rf"\\(?P<cmd>color|textcolor)\s*\{{\s*(?P<color>{names})\s*\}}")
    if by_macro:
        alts.append(rf"\\(?P<macro>{'|'.join(re.escape(n) for n in by_macro)})(?![a-zA-Z@])")
    if by_env:
        alts.append(rf"\\begin\s*\{{\s*(?P<env>{'|'.join(re.escape(n) for n in by_env)})\s*\}}")
    if not alts:
        return []
    pattern = re.compile("|".join(alts))

    s = src.text
    markers: list[Marker] = []
    last_end = -1
    for m in pattern.finditer(s, src.body_start, src.body_end):
        if m.start() < last_end:
            continue  # nested in the previous marker
        mk = _scope(s, m, specs, by_color, by_macro, by_env, src.body_end)
        if mk is None:
            continue
        if mk.spec_index in color_of:
            mk.tex_color = src.colors.get(color_of[mk.spec_index])
        markers.append(mk)
        last_end = mk.end

    _attach_notes(src, markers)
    for n, mk in enumerate(markers, start=1):
        mk.order = n
    return markers


def _scope(s: str, m: re.Match, specs, by_color, by_macro, by_env, limit: int) -> Optional[Marker]:
    gd = m.groupdict()
    if gd.get("cmd"):
        idx = by_color[gd["color"]]
        if gd["cmd"] == "textcolor":
            grp = read_group(s, skip_ws(s, m.end()))
            if grp is None:
                return None
            return Marker("textcolor", gd["color"], specs[idx], m.start(), grp[1] + 1, grp[0], grp[1], idx)
        body_end = color_scope_end(s, m.end(), limit)
        start, end = m.start(), body_end
        k = m.start() - 1
        while k >= 0 and s[k] in " \t\n":
            k -= 1
        if k >= 0 and s[k] == "{" and body_end < len(s) and s[body_end] == "}":
            start, end = k, body_end + 1
        return Marker("color", gd["color"], specs[idx], start, end, m.end(), body_end, idx)

    if gd.get("macro"):
        idx = by_macro[gd["macro"]]
        k = m.end()
        if k < len(s) and s[k] == "*":
            k += 1
        args, end = read_args(s, k, 1)
        if not args:
            return None
        return Marker("macro", gd["macro"], specs[idx], m.start(), end, args[0][0], args[0][1], idx)

    env = gd["env"]
    idx = by_env[env]
    k = skip_ws(s, m.end())
    while (opt := read_optional(s, k)) is not None:
        k = skip_ws(s, opt[1] + 1)
    end_start, after = find_env_end(s, m.end(), env)
    return Marker("env", env, specs[idx], m.start(), min(after, limit), k, min(end_start, limit), idx)


def color_scope_end(s: str, i: int, limit: int) -> int:
    depth = 0  # brace / \begingroup nesting relative to the \color command
    env_depth = 0
    k = i
    while k < limit:
        c = s[k]
        if c == "\\":
            cmd = read_command(s, k)
            if cmd is None:
                k += 1
                continue
            name, e = cmd
            if name == "begin":
                env_depth += 1
            elif name == "end":
                if env_depth == 0:
                    return k
                env_depth -= 1
            elif name in ("begingroup", "bgroup"):
                depth += 1
            elif name in ("endgroup", "egroup"):
                if depth == 0:
                    return k
                depth -= 1
            elif name in ("color", "normalcolor") and depth == 0 and env_depth == 0:
                return k
            k = e
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return k
            depth -= 1
        k += 1
    return limit


def _attach_notes(src: TexSource, markers: list[Marker]) -> None:
    """Notes inside a marker belong to it; otherwise a note on the line just above the marker's line.

    The reader drops a comment together with its line break, so a note on the line above ends up on
    the marker's own line: nothing but that line's text (and no other marker) lies in between.
    """
    notes = sorted(src.notes, key=lambda n: n.pos)
    used: set[int] = set()
    prev_end = -1
    for mk in markers:
        inside = [i for i, n in enumerate(notes) if mk.start <= n.pos <= mk.end and i not in used]
        if not inside:
            before = [
                i for i, n in enumerate(notes)
                if prev_end <= n.pos <= mk.start and i not in used and "\n" not in src.text[n.pos : mk.start]
            ]
            inside = before[-1:]
            # consecutive %@note lines directly before the marker form one note
            while inside and inside[0] > 0 and (inside[0] - 1) not in used:
                prev = notes[inside[0] - 1]
                if src.text[prev.pos : notes[inside[0]].pos].strip():
                    break
                inside.insert(0, inside[0] - 1)
        if inside:
            mk.note = "\n".join(notes[i].text for i in inside)
            used.update(inside)
        prev_end = mk.end
