import pymupdf
import pytest

from notepdf.config import Config
from notepdf.matcher import Matcher, exact_pattern, loose_pattern, split_gaps
from notepdf.textindex import DocText

from .conftest import LOREM


def matcher_for(pdf):
    doc = pymupdf.open(pdf)
    return Matcher(DocText.from_pdf(doc), doc.page_count), doc


def entry(**fields):
    return Config.model_validate({"annotations": [fields]}).entries()[0]


def matched_text(m, span):
    return "".join(c.c if c.bbox else " " for c in m.doc.chars[span.start : span.end])


def test_split_gaps_and_patterns():
    assert split_gaps("a {{gap}} b {{ gap:5 }}") == ["a ", 60, " b ", 5]
    assert loose_pattern("Fig. {{gap:5}} shows") == r"Fig.{0,5}?shows"
    assert loose_pattern("{{gap}} edge {{gap:3}}") == "edge"
    assert exact_pattern("a-b c").startswith("a[-")


def test_normalized_match_spans_lines(make_pdf):
    m, _ = matcher_for(make_pdf(LOREM))
    res = m.find(entry(text="significantly outperforms the baseline on every benchmark we tried"))
    (span,) = res.spans
    lines = {c.line for c in m.doc.chars[span.start : span.end] if c.bbox}
    assert len(lines) >= 2
    assert matched_text(m, span).split() == "significantly outperforms the baseline on every benchmark we tried".split()


def test_normalized_ignores_case_punctuation_and_ligatures(make_pdf):
    m, _ = matcher_for(make_pdf("The ﬁnal “state-of-the-art” results — finally."))
    assert m.find(entry(text='the FINAL "state of the art" results')).spans
    assert not m.find(entry(text="the FINAL results", case_sensitive=True)).spans


def test_exact_mode(make_pdf):
    m, _ = matcher_for(make_pdf("He said “don’t” – twice."))
    assert m.find(entry(text="said \"don't\" - twice", match="exact")).spans
    assert not m.find(entry(text="said dont twice", match="exact")).spans


def test_hyphenated_line_break(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "We study the re-", fontsize=11)
    page.insert_text((72, 114), "vision of state-of-", fontsize=11)
    page.insert_text((72, 128), "the-art papers.", fontsize=11)
    doc.save(tmp_path / "h.pdf")
    m, _ = matcher_for(tmp_path / "h.pdf")
    assert m.find(entry(text="the revision of state-of-the-art papers", match="exact")).spans
    assert m.find(entry(text="the revision of state-of-the-art papers")).spans


def test_gaps(make_pdf):
    m, _ = matcher_for(make_pdf("As shown in prior work [12, 15], the loss converges fast."))
    (span,) = m.find(entry(text="prior work {{gap:10}}, the loss")).spans
    assert "[12, 15]" in matched_text(m, span)
    assert not m.find(entry(text="prior work {{gap:2}} the loss")).spans


def test_regex(make_pdf):
    m, _ = matcher_for(make_pdf("See Table 3 and Table 12 for details."))
    res = m.find(entry(regex=r"Table\s+\d+", occurrence="all"))
    assert [matched_text(m, s) for s in res.spans] == ["Table 3", "Table 12"]


@pytest.mark.parametrize(
    "occurrence, expected",
    [("first", [0]), ("all", [0, 1, 2]), (2, [1]), ([1, 3], [0, 2])],
)
def test_occurrence(make_pdf, occurrence, expected):
    m, _ = matcher_for(make_pdf("alpha beta. alpha beta. alpha beta."))
    every = m.find(entry(text="alpha beta", occurrence="all")).spans
    got = m.find(entry(text="alpha beta", occurrence=occurrence)).spans
    assert [every.index(s) for s in [next(e for e in every if e.start == g.start) for g in got]] == expected


def test_missing_occurrence_warns(make_pdf):
    m, _ = matcher_for(make_pdf("alpha beta."))
    res = m.find(entry(text="alpha beta", occurrence=3))
    assert not res.spans and "only 1 found" in res.warnings[0]


def test_pages_and_cross_page(make_pdf):
    m, _ = matcher_for(make_pdf("Our proposed method wins.", "Our proposed method wins again. It ends here", "and continues on the next page."))
    (span,) = m.find(entry(text="our proposed method", pages=2)).spans
    assert m.doc.chars[span.start].page == 1
    (span,) = m.find(entry(text="it ends here and continues on")).spans
    assert {c.page for c in m.doc.chars[span.start : span.end] if c.bbox} == {1, 2}


def test_context_disambiguates(make_pdf):
    m, _ = matcher_for(make_pdf("First, our method is fast. In contrast to prior work, our method is accurate."))
    (span,) = m.find(entry(text="our method", context_before="In contrast to prior work")).spans
    assert matched_text(m, span) == "our method" and "accurate" in m.doc.raw_text[span.end : span.end + 20]
    (span,) = m.find(entry(text="our method", context_after="is fast")).spans
    assert span.start < 20


def test_sequential_cursor(make_pdf):
    m, _ = matcher_for(make_pdf("alpha one. beta two. alpha three."))
    beta = m.find(entry(text="beta two", sequential=True)).spans[0]
    (span,) = m.find(entry(text="alpha", sequential=True), cursor=beta.end).spans
    assert span.start > beta.end
    res = m.find(entry(text="alpha one", sequential=True), cursor=beta.end)
    assert res.spans and "out of order" in res.warnings[0]


def test_word_boundary_preference(make_pdf):
    m, _ = matcher_for(make_pdf("We start. The art of matching."))
    (span,) = m.find(entry(text="art")).spans
    assert matched_text(m, span) == "art" and m.doc.chars[span.start - 1].c == " "
    m2, _ = matcher_for(make_pdf("We start now.", name="b.pdf"))
    assert m2.find(entry(text="art")).spans  # inside a word is still allowed when it's the only match
    assert not m2.find(entry(text="art", whole_word=True)).spans


def test_fuzzy_fallback(make_pdf):
    pytest.importorskip("rapidfuzz")
    m, _ = matcher_for(make_pdf("Anomaly Transformer combines association discrepancy with reconstruction error."))
    text = "Anomaly Transformer combines association discrepancy with reconstruction errors"
    assert not m.find(entry(text=text)).spans
    res = m.find(entry(text=text, fuzzy_fallback=True))
    (span,) = res.spans
    assert span.mode == "fuzzy" and matched_text(m, span).endswith("error")
    assert "fuzzy match" in res.warnings[0]


def test_split_fallback_matches_sentences(make_pdf):
    m, _ = matcher_for(make_pdf("The first sentence stays the same. A second sentence was later rewritten. The third sentence is also here."))
    text = "The first sentence stays the same. A totally different second sentence here. The third sentence is also here."
    res = m.find(entry(text=text, split_fallback=True))
    assert len(res.spans) == 2 and "2/3 sentences" in res.warnings[0]


def test_split_fallback_merges_adjacent_sentences(make_pdf):
    m, _ = matcher_for(make_pdf("Sentence number one is here. Sentence number two is here. Unrelated text."))
    text = "Sentence number one is here. Sentence number two is here. A third sentence that is absent."
    res = m.find(entry(text=text, split_fallback=True))
    (span,) = res.spans  # the two found sentences are adjacent, so they become one highlight
    assert span.mode == "split" and matched_text(m, span) == "Sentence number one is here. Sentence number two is here."


def test_text_color_preference(tmp_path):
    from .conftest import build_pdf

    pdf = build_pdf(tmp_path / "c.pdf", ["<p>We further evaluate on new datasets.</p><p style='color:#0000FF'>We further evaluate on new datasets.</p>"])
    m, _ = matcher_for(pdf)
    plain = m.find(entry(text="We further evaluate on new datasets")).spans[0]
    colored = m.find(entry(text="We further evaluate on new datasets", text_color="#0000FF")).spans[0]
    assert colored.start > plain.start and colored.color_share == 1.0


def test_edge_gap_extension(make_pdf):
    m, _ = matcher_for(make_pdf("A reference to Table 2. More text."))
    (span,) = m.find(entry(text="A reference to Table {{gap:40}}.")).spans
    assert matched_text(m, span) == "A reference to Table 2."
    (span,) = m.find(entry(text="reference to Table")).spans
    assert matched_text(m, span) == "reference to Table"
