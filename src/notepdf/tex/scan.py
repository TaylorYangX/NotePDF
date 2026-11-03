"""Low-level LaTeX scanning helpers shared by the marker finder and the detexer.

All positions are indices into the comment-free source produced by ``reader.read_tex``.
"""

from __future__ import annotations

import re
from typing import Optional

CMD_RE = re.compile(r"\\([a-zA-Z@]+\*?|.)", re.S)
BEGIN_END_RE = re.compile(r"\\(begin|end)\s*\{([^}]*)\}")


def read_command(s: str, i: int) -> Optional[tuple[str, int]]:
    """``\\name`` (or ``\\name*``, or a control symbol like ``\\%``) at ``i`` -> (name, end)."""
    m = CMD_RE.match(s, i)
    return (m.group(1), m.end()) if m else None


def skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\n":
        i += 1
    return i


def read_group(s: str, i: int) -> Optional[tuple[int, int]]:
    """Brace group starting at ``s[i] == '{'`` -> (content_start, content_end); the group ends at content_end + 1."""
    if i >= len(s) or s[i] != "{":
        return None
    depth = 0
    k = i
    while k < len(s):
        c = s[k]
        if c == "\\":
            k += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (i + 1, k)
        k += 1
    return (i + 1, len(s))  # unbalanced: run to the end


def read_optional(s: str, i: int) -> Optional[tuple[int, int]]:
    """``[...]`` at ``i`` (brace-aware) -> (content_start, content_end)."""
    if i >= len(s) or s[i] != "[":
        return None
    depth = 0
    k = i + 1
    while k < len(s):
        c = s[k]
        if c == "\\":
            k += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "]" and depth <= 0:
            return (i + 1, k)
        k += 1
    return None


def read_args(s: str, i: int, n_mandatory: int, optional: bool = True) -> tuple[list[tuple[int, int]], int]:
    """Skip optional ``[..]`` args and read ``n_mandatory`` braced args. Returns (arg spans, end)."""
    args: list[tuple[int, int]] = []
    k = i
    while True:
        j = skip_ws(s, k)
        if optional and (opt := read_optional(s, j)):
            k = opt[1] + 1
            continue
        if len(args) >= n_mandatory:
            return args, k
        grp = read_group(s, j)
        if grp is None:
            return args, k
        args.append(grp)
        k = grp[1] + 1


def find_env_end(s: str, i: int, env: str) -> tuple[int, int]:
    """Position of the ``\\end{env}`` matching an already-opened ``\\begin{env}`` -> (start, after)."""
    depth = 1
    for m in BEGIN_END_RE.finditer(s, i):
        if m.group(2).strip() != env:
            continue
        depth += 1 if m.group(1) == "begin" else -1
        if depth == 0:
            return m.start(), m.end()
    return len(s), len(s)
