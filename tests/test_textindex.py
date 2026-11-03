import pymupdf

from notepdf.textindex import LINE_SEP, PAGE_SEP, SOFT_HYPHEN, DocText, canon, loose_chars


def _doc_with_lines(tmp_path, lines_per_page):
    doc = pymupdf.open()
    for lines in lines_per_page:
        page = doc.new_page()
        for k, line in enumerate(lines):
            page.insert_text((72, 100 + 14 * k), line, fontsize=11)
    path = tmp_path / "lines.pdf"
    doc.save(path)
    return pymupdf.open(path)


def test_normalization_helpers():
    assert loose_chars("ﬁnal “naïve” re-run — 3.5%") == "finalnaivererun35"
    assert canon("“quoted” – dash ’") == "\"quoted\" - dash '"


def test_raw_stream_has_separators_and_boxes(tmp_path):
    doc = _doc_with_lines(tmp_path, [["first line", "second line"], ["third"]])
    dt = DocText.from_pdf(doc)
    raw = dt.raw_text
    assert raw == f"first line{LINE_SEP}second line{PAGE_SEP}third"
    assert all((c.bbox is None) == (c.c in (LINE_SEP, PAGE_SEP)) for c in dt.chars)
    assert {c.page for c in dt.chars if c.c == "t" and c.bbox} == {0, 1}


def test_views_map_back_to_raw(tmp_path):
    doc = _doc_with_lines(tmp_path, [["Alpha beta,", "gamma-delta."]])
    dt = DocText.from_pdf(doc)
    assert dt.loose.text == "Alphabetagammadelta"
    for pos, ri in enumerate(dt.loose.raw):
        assert loose_chars(dt.chars[ri].c) == dt.loose.text[pos]
    assert dt.exact.text == "Alpha beta, gamma-delta."
    s, e = dt.exact.to_raw_span(6, 10)
    assert "".join(c.c for c in dt.chars[s:e]) == "beta"


def test_line_end_hyphen_becomes_soft_hyphen(tmp_path):
    doc = _doc_with_lines(tmp_path, [["We study re-", "vision control."]])
    dt = DocText.from_pdf(doc)
    assert f"re{SOFT_HYPHEN}vision" in dt.exact.text
    assert "revision" in dt.loose.text


def test_page_bounds_and_ranges(tmp_path):
    doc = _doc_with_lines(tmp_path, [["one"], ["two"], ["three"]])
    dt = DocText.from_pdf(doc)
    assert dt.loose.text[slice(*dt.loose.page_bounds[1])] == "two"
    assert dt.ranges_for_pages(dt.loose, [0, 1]) == [(0, 6)]
    assert dt.ranges_for_pages(dt.loose, [0, 2]) == [(0, 3), (6, 11)]
