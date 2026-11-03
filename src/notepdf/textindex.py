"""Character-level text of a PDF, with normalized views that map back to the original characters.

Every character on the page comes from ``page.get_text("rawdict")`` together with its box and color.
Line, block and page breaks are inserted as separator characters without a box, so a match can run
across lines, columns and pages and still be turned back into per-line quads.

Two searchable views are built on top of the raw stream:

* ``exact``  - NFKC, curly quotes/dashes made ASCII, whitespace runs collapsed to one space, and a
  hyphen at the end of a line turned into a soft hyphen so "re-\\nvision" can match "revision".
* ``loose``  - only letters and digits, accents removed. Insensitive to punctuation, quotes, dashes,
  hyphenation and line/column breaks. This is what ``match: normalized`` searches.
"""

from __future__ import annotations

import bisect
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

import pymupdf

LINE_SEP = "\n"
PAGE_SEP = "\f"
SOFT_HYPHEN = "­"
TEXT_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP

_CANON = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
        " ": " ", " ": " ", " ": " ", " ": " ",
    }
)
_HYPHENS = "-­‐‑"


def canon(s: str) -> str:
    """Normalization shared by the exact view and exact-mode needles."""
    return unicodedata.normalize("NFKC", s).translate(_CANON)


def loose_chars(s: str) -> str:
    """Letters and digits of ``s`` with accents and compatibility forms folded (e.g. 'ﬁ' -> 'fi', 'é' -> 'e')."""
    out = []
    for ch in unicodedata.normalize("NFKD", s):
        if ch.isalnum() and not unicodedata.combining(ch):
            out.append(ch)
    return "".join(out)


@dataclass(slots=True)
class Char:
    c: str
    page: int  # 0-based page index
    line: int  # document-wide line id
    bbox: Optional[tuple[float, float, float, float]]  # None for inserted separators
    color: Optional[int] = None  # sRGB int as reported by PyMuPDF
    horizontal: bool = True


@dataclass
class View:
    text: str
    raw: list[int]  # view position -> raw char index
    page_bounds: dict[int, tuple[int, int]] = field(default_factory=dict)  # page -> [start, end) in view

    def to_raw_span(self, start: int, end: int) -> tuple[int, int]:
        return self.raw[start], self.raw[end - 1] + 1

    def from_raw(self, raw_index: int) -> int:
        """First view position at or after ``raw_index``."""
        return bisect.bisect_left(self.raw, raw_index)


class DocText:
    def __init__(self, chars: list[Char], pages: list[int]):
        self.chars = chars
        self.pages = pages
        self.exact = self._build_exact()
        self.loose = self._build_loose()

    @classmethod
    def from_pdf(cls, doc: pymupdf.Document, pages: Optional[Iterable[int]] = None) -> "DocText":
        pages = list(range(doc.page_count)) if pages is None else list(pages)
        chars: list[Char] = []
        line_id = 0
        for pno in pages:
            if chars:
                chars.append(Char(PAGE_SEP, pno, line_id, None))
            page_dict = doc[pno].get_text("rawdict", flags=TEXT_FLAGS)
            first_line = True
            for block in page_dict["blocks"]:
                if block.get("type", 0) != 0:
                    continue
                for line in block["lines"]:
                    line_chars = [
                        Char(ch["c"], pno, line_id, tuple(ch["bbox"]), span["color"], _is_horizontal(line["dir"]))
                        for span in line["spans"]
                        for ch in span["chars"]
                    ]
                    if not line_chars:
                        continue
                    if not first_line:
                        chars.append(Char(LINE_SEP, pno, line_id, None))
                    chars.extend(line_chars)
                    first_line = False
                    line_id += 1
        return cls(chars, pages)

    @property
    def raw_text(self) -> str:
        return "".join(c.c for c in self.chars)

    def colors_present(self) -> set[int]:
        return {c.color for c in self.chars if c.color is not None and c.bbox is not None}

    # -- view construction -------------------------------------------------------------------------

    def _build_exact(self) -> View:
        text: list[str] = []
        raw: list[int] = []
        chars = self.chars
        n = len(chars)
        i = 0
        while i < n:
            ch = chars[i]
            if ch.c.isspace():
                j = i
                while j < n and chars[j].c.isspace():
                    j += 1
                if text and text[-1] != " ":
                    text.append(" ")
                    raw.append(i)
                i = j
                continue
            if ch.c in _HYPHENS and i + 1 < n and chars[i + 1].bbox is None and text and text[-1].isalpha():
                text.append(SOFT_HYPHEN)
                raw.append(i)
                i += 2  # skip the line break; the next line starts right after the soft hyphen
                continue
            for out in canon(ch.c):
                text.append(" " if out.isspace() else out)
                raw.append(i)
            i += 1
        return View("".join(text), raw, self._page_bounds(raw))

    def _build_loose(self) -> View:
        text: list[str] = []
        raw: list[int] = []
        for i, ch in enumerate(self.chars):
            if ch.bbox is None:
                continue
            for out in loose_chars(ch.c):
                text.append(out)
                raw.append(i)
        return View("".join(text), raw, self._page_bounds(raw))

    def _page_bounds(self, raw: list[int]) -> dict[int, tuple[int, int]]:
        bounds: dict[int, tuple[int, int]] = {}
        for pos, ri in enumerate(raw):
            p = self.chars[ri].page
            lo, _ = bounds.get(p, (pos, pos))
            bounds[p] = (lo, pos + 1)
        return bounds

    def ranges_for_pages(self, view: View, pages: list[int]) -> list[tuple[int, int]]:
        """Contiguous [start, end) view ranges covering ``pages`` (adjacent pages are merged)."""
        out: list[tuple[int, int]] = []
        prev_page = None
        for p in sorted(pages):
            if p not in view.page_bounds:
                prev_page = None
                continue
            lo, hi = view.page_bounds[p]
            if out and prev_page is not None and p == prev_page + 1:
                out[-1] = (out[-1][0], hi)
            else:
                out.append((lo, hi))
            prev_page = p
        return out


def _is_horizontal(direction: tuple[float, float]) -> bool:
    return abs(direction[1]) < 1e-3 and direction[0] > 0
