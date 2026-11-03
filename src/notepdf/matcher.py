"""Find the characters an entry refers to.

Needles may contain ``{{gap}}`` / ``{{gap:N}}`` placeholders that skip up to N characters
(default 60). TeX-generated entries use them for citations, references and inline math, whose
rendered form can't be predicted from the source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Union

from .colors import RGB, color_distance, from_srgb_int
from .config import Entry, pages_to_indices
from .messages import Msg
from .textindex import PAGE_SEP, SOFT_HYPHEN, DocText, View, canon, loose_chars

GAP_RE = re.compile(r"\{\{\s*gap\s*(?::\s*(\d+))?\s*\}\}")
DEFAULT_GAP = 60
CONTEXT_WINDOW = 120  # loose chars of slack allowed between a context string and the match
COLOR_TOLERANCE = 0.12
COLOR_SHARE = 0.6  # fraction of a match's characters that must be in text_color to count as "colored"
MIN_FUZZY_CHARS = 12
SENTENCE_RE = re.compile(r"(?<=[.!?;:])\s+(?=\S)")
MIN_SENTENCE_CHARS = 15
MERGE_SLACK = 4  # letters/digits allowed between two sentence matches that are merged into one span

try:
    from rapidfuzz import fuzz as _fuzz
except ImportError:  # optional dependency
    _fuzz = None


@dataclass
class Span:
    start: int  # raw char index, inclusive
    end: int  # raw char index, exclusive
    mode: str  # "exact" | "normalized" | "regex" | "fuzzy"
    score: float = 100.0
    color_share: Optional[float] = None


@dataclass
class MatchResult:
    spans: list[Span] = field(default_factory=list)
    candidates: int = 0
    warnings: list[str] = field(default_factory=list)


def split_gaps(text: str) -> list[Union[str, int]]:
    """``"a {{gap:5}} b"`` -> ``["a ", 5, " b"]`` with empty literals removed."""
    parts: list[Union[str, int]] = []
    pos = 0
    for m in GAP_RE.finditer(text):
        if m.start() > pos:
            parts.append(text[pos : m.start()])
        parts.append(int(m.group(1)) if m.group(1) else DEFAULT_GAP)
        pos = m.end()
    if pos < len(text):
        parts.append(text[pos:])
    return parts


def _in_gap(text: str, k: int) -> bool:
    return any(m.start() <= k < m.end() for m in GAP_RE.finditer(text))


def exact_pattern(text: str) -> str:
    out: list[str] = []
    for part in split_gaps(text):
        if isinstance(part, int):
            out.append(f"[\\s\\S]{{0,{int(part * 1.5)}}}?")
            continue
        s = re.sub(r"\s+", " ", canon(part))
        for k, ch in enumerate(s):
            if ch == " ":
                out.append(" ?")
            elif ch == "-":
                out.append(f"[-{SOFT_HYPHEN}]")
            else:
                out.append(re.escape(ch))
                if ch.isalnum() and k + 1 < len(s) and s[k + 1].isalnum():
                    out.append(f"{SOFT_HYPHEN}?")  # word hyphenated at a line break
    return _strip_edges("".join(out))


def loose_pattern(text: str) -> str:
    out = []
    for part in split_gaps(text):
        out.append(f".{{0,{part}}}?" if isinstance(part, int) else re.escape(loose_chars(part)))
    return _strip_edges("".join(out))


def _strip_edges(pattern: str) -> str:
    # Leading/trailing gaps and optional spaces only widen a match; drop them.
    edge = r"(?:\[\\s\\S\]\{0,\d+\}\?|\.\{0,\d+\}\?| \?)"
    return re.sub(rf"^{edge}+|{edge}+$", "", pattern)


class Matcher:
    def __init__(self, doctext: DocText, page_count: int):
        self.doc = doctext
        self.page_count = page_count
        self._present_colors: Optional[set[int]] = None

    def find(self, entry: Entry, cursor: Optional[int] = None) -> MatchResult:
        spec, style = entry.spec, entry.style
        result = MatchResult()
        pages = pages_to_indices(spec.pages, self.page_count)
        flags = 0 if style.case_sensitive else re.IGNORECASE

        if spec.regex is not None:
            view, mode, pattern = self.doc.exact, "regex", spec.regex
        elif style.match == "exact":
            view, mode, pattern = self.doc.exact, "exact", exact_pattern(spec.text or "")
        else:
            view, mode, pattern = self.doc.loose, "normalized", loose_pattern(spec.text or "")
        if not pattern:
            result.warnings.append(Msg("nothing_searchable", "nothing searchable in the text (only punctuation or gaps)"))
            return result

        ranges = self.doc.ranges_for_pages(view, pages)
        cands: list[Span] = []
        if style.match != "fuzzy" or spec.regex is not None:
            cands = self._regex_search(re.compile(pattern, flags), view, ranges, mode)
        cands = [c for c in cands if self._context_ok(c, spec.context_before, spec.context_after)]
        if style.whole_word:
            cands = [c for c in cands if self._on_word_boundaries(c)]

        if not cands and spec.text is not None and (style.match == "fuzzy" or style.fuzzy_fallback):
            if _fuzz is None:
                result.warnings.append(Msg("fuzzy_unavailable", "fuzzy matching needs rapidfuzz: uv sync --extra fuzzy"))
            else:
                cands = self._fuzzy_search(spec.text, ranges, style.fuzzy_threshold, style.case_sensitive, cursor)
                cands = [c for c in cands if self._context_ok(c, spec.context_before, spec.context_after)]
                if cands and style.match != "fuzzy":
                    score = round(cands[0].score)
                    result.warnings.append(Msg("fuzzy_match", f"no exact match; fuzzy match with score {score}", score=score))

        if not cands and spec.text is not None and style.split_fallback:
            return self._find_by_sentences(entry, cursor, result)

        result.candidates = len(cands)
        if not cands:
            return result

        if spec.text_color is not None:
            cands = self._prefer_colored(cands, spec.text_color, result)
        boundary = [c for c in cands if self._on_word_boundaries(c)]
        if boundary:
            cands = boundary

        result.spans = self._choose(cands, style.occurrence, cursor if style.sequential else None, result)
        if spec.text is not None:
            result.spans = [self._extend_edges(sp, spec.text) for sp in result.spans]
        return result

    def _find_by_sentences(self, entry: Entry, cursor: Optional[int], result: MatchResult) -> MatchResult:
        """Match a long text piece by piece and merge the pieces that turn out to be adjacent."""
        parts = [
            p for p in SENTENCE_RE.split(entry.spec.text or "")
            if len(loose_chars(GAP_RE.sub("", p))) >= MIN_SENTENCE_CHARS
        ]
        if len(parts) < 2:
            return result
        sub_style = entry.style.model_copy(update={"split_fallback": False, "occurrence": "first", "sequential": True})
        local = cursor if entry.style.sequential else None
        spans: list[Span] = []
        for part in parts:
            sub = Entry(entry.index, entry.spec.model_copy(update={"text": part}), sub_style)
            found = self.find(sub, local)
            if found.spans:
                spans.append(found.spans[0])
                local = found.spans[0].end
        if not spans:
            return result
        result.spans = self._merge(sorted(spans, key=lambda sp: sp.start))
        result.candidates = 1
        if len(spans) < len(parts):
            result.warnings.append(
                Msg("partial_sentences", f"partial match: {len(spans)}/{len(parts)} sentences found", found=len(spans), total=len(parts))
            )
        return result

    def _merge(self, spans: list[Span]) -> list[Span]:
        out = [spans[0]]
        for sp in spans[1:]:
            prev = out[-1]
            between = self.doc.chars[prev.end : sp.start] if sp.start >= prev.end else []
            if sp.start >= prev.end and sum(1 for c in between if c.bbox is not None and c.c.isalnum()) <= MERGE_SLACK:
                out[-1] = Span(prev.start, sp.end, "split", min(prev.score, sp.score))
            else:
                out.append(sp)
        return out

    # -- search ------------------------------------------------------------------------------------

    def _regex_search(self, pat: re.Pattern, view: View, ranges: list[tuple[int, int]], mode: str) -> list[Span]:
        out = []
        for lo, hi in ranges:
            for m in pat.finditer(view.text, lo, hi):
                if m.end() > m.start():
                    s, e = self._trim(*view.to_raw_span(m.start(), m.end()))
                    if e > s:
                        out.append(Span(s, e, mode))
        return out

    def _fuzzy_search(
        self, text: str, ranges: list[tuple[int, int]], threshold: float, case_sensitive: bool, cursor: Optional[int]
    ) -> list[Span]:
        needle = "".join(loose_chars(p) for p in split_gaps(text) if isinstance(p, str))
        if len(needle) < MIN_FUZZY_CHARS:
            return []
        view = self.doc.loose
        if not case_sensitive:
            needle = needle.lower()
        # Search after the cursor first so sequential entries stay in order.
        search_ranges = ranges
        if cursor is not None:
            c = view.from_raw(cursor)
            after = [(max(lo, c), hi) for lo, hi in ranges if hi > c]
            search_ranges = after + ranges if after else ranges
        for lo, hi in search_ranges:
            hay = view.text[lo:hi]
            res = _fuzz.partial_ratio_alignment(needle, hay if case_sensitive else hay.lower(), score_cutoff=threshold)
            if res is not None and res.dest_end > res.dest_start:
                s, e = self._snap_to_words(*view.to_raw_span(lo + res.dest_start, lo + res.dest_end))
                return [Span(s, e, "fuzzy", score=res.score)]
        return []

    def _snap_to_words(self, start: int, end: int) -> tuple[int, int]:
        chars = self.doc.chars
        while start > 0 and chars[start - 1].c.isalnum() and chars[start - 1].bbox is not None:
            start -= 1
        while end < len(chars) and chars[end].c.isalnum() and chars[end].bbox is not None:
            end += 1
        return start, end

    def _extend_edges(self, span: Span, text: str) -> Span:
        """Cover what edge gaps and edge punctuation stand for, e.g. the "2." of "Table~\\ref{t}."."""
        chars = self.doc.chars
        n = len(chars)
        alnum = [k for k, ch in enumerate(text) if ch.isalnum() and not _in_gap(text, k)]
        if not alnum:
            return span
        head, tail = text[: alnum[0]], text[alnum[-1] + 1 :]
        start, end = span.start, span.end

        tail_gap = sum(p for p in split_gaps(tail) if isinstance(p, int))
        tail_punct = "".join(canon(GAP_RE.sub("", tail)).split())
        if tail_gap:
            limit = min(n, end + int(tail_gap * 1.5) + len(tail_punct) + 2)
            k = end
            if tail_punct:
                while k < limit and chars[k].c != PAGE_SEP and canon(chars[k].c) != tail_punct[0]:
                    k += 1
                if k < limit and canon(chars[k].c) == tail_punct[0]:
                    end = k + 1
            else:
                while k < limit and chars[k].c.isspace() and chars[k].c != PAGE_SEP:
                    k += 1
                while k < limit and not chars[k].c.isspace() and chars[k].bbox is not None:
                    k += 1
                end = k
        elif tail_punct:
            k = end
            for want in tail_punct:
                if k < n and canon(chars[k].c) == want:
                    k += 1
                else:
                    break
            end = k

        head_gap = sum(p for p in split_gaps(head) if isinstance(p, int))
        head_punct = "".join(canon(GAP_RE.sub("", head)).split())
        if head_gap:
            k = start
            limit = max(0, start - int(head_gap * 1.5) - 2)
            while k > limit and chars[k - 1].c.isspace() and chars[k - 1].c != PAGE_SEP:
                k -= 1
            while k > limit and not chars[k - 1].c.isspace() and chars[k - 1].bbox is not None:
                k -= 1
            start = k if k < start else start
        elif head_punct:
            k = start
            for want in reversed(head_punct):
                if k > 0 and canon(chars[k - 1].c) == want:
                    k -= 1
                else:
                    break
            start = k
        if (start, end) == (span.start, span.end):
            return span
        s, e = self._trim(start, end)
        return Span(s, e, span.mode, span.score, span.color_share)

    def _trim(self, start: int, end: int) -> tuple[int, int]:
        chars = self.doc.chars
        while start < end and (chars[start].bbox is None or chars[start].c.isspace()):
            start += 1
        while end > start and (chars[end - 1].bbox is None or chars[end - 1].c.isspace()):
            end -= 1
        return start, end

    # -- filters -----------------------------------------------------------------------------------

    def _context_ok(self, span: Span, before: Optional[str], after: Optional[str]) -> bool:
        loose = self.doc.loose
        if before:
            ctx = loose_chars(before).lower()
            ls = loose.from_raw(span.start)
            if ctx not in loose.text[max(0, ls - len(ctx) - CONTEXT_WINDOW) : ls].lower():
                return False
        if after:
            ctx = loose_chars(after).lower()
            le = loose.from_raw(span.end)
            if ctx not in loose.text[le : le + len(ctx) + CONTEXT_WINDOW].lower():
                return False
        return True

    def _on_word_boundaries(self, span: Span) -> bool:
        chars = self.doc.chars
        before = chars[span.start - 1].c if span.start > 0 else " "
        after = chars[span.end].c if span.end < len(chars) else " "
        return not (before.isalnum() and chars[span.start].c.isalnum()) and not (
            after.isalnum() and chars[span.end - 1].c.isalnum()
        )

    def _prefer_colored(self, cands: list[Span], target: RGB, result: MatchResult) -> list[Span]:
        if not self._color_in_doc(target):
            return cands  # e.g. a "clean" build where revcolor was set to black
        for c in cands:
            c.color_share = self._color_share(c, target)
        colored = [c for c in cands if (c.color_share or 0) >= COLOR_SHARE]
        return colored or cands  # the color may just be used elsewhere (e.g. hyperref links)

    def _color_in_doc(self, target: RGB) -> bool:
        if self._present_colors is None:
            self._present_colors = self.doc.colors_present()
        return any(color_distance(from_srgb_int(c), target) <= COLOR_TOLERANCE for c in self._present_colors)

    def _color_share(self, span: Span, target: RGB) -> float:
        relevant = [c for c in self.doc.chars[span.start : span.end] if c.bbox is not None and c.c.isalnum()]
        if not relevant:
            return 0.0
        hits = sum(1 for c in relevant if c.color is not None and color_distance(from_srgb_int(c.color), target) <= COLOR_TOLERANCE)
        return hits / len(relevant)

    # -- occurrence selection ----------------------------------------------------------------------

    def _choose(self, cands: list[Span], occurrence, cursor: Optional[int], result: MatchResult) -> list[Span]:
        if occurrence == "all":
            return cands
        if occurrence == "first":
            if cursor is None:
                return [cands[0]]
            after = [c for c in cands if c.start >= cursor]
            if after:
                return [after[0]]
            result.warnings.append(Msg("out_of_order", "found only before the previous sequential match (out of order)"))
            return [min(cands, key=lambda c: abs(c.start - cursor))]
        wanted = [occurrence] if isinstance(occurrence, int) else list(occurrence)
        picked = [cands[n - 1] for n in wanted if n <= len(cands)]
        missing = [n for n in wanted if n > len(cands)]
        if missing:
            wanted_text = ", ".join(map(str, missing))
            result.warnings.append(
                Msg("occurrence_missing", f"occurrence {wanted_text} requested but only {len(cands)} found", wanted=wanted_text, found=len(cands))
            )
        return picked
