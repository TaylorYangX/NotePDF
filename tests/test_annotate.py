import pymupdf
import pytest
from pypdf import PdfReader

from notepdf.annotate import NM_PREFIX, list_annots
from notepdf.apply import apply, default_output
from notepdf.config import ConfigError

from .conftest import LOREM

TARGET = "significantly outperforms the baseline on every benchmark we tried"


def markups(pdf):
    with pymupdf.open(pdf) as doc:
        return [r for r in list_annots(doc) if r["type"] != "Text"]


def test_highlight_written_like_a_viewer_would(make_pdf, config_for, tmp_path):
    out = tmp_path / "out.pdf"
    cfg = config_for(make_pdf(LOREM), [{"text": TARGET, "comment": "R2.3", "color": "#A5D6A7"}], out, defaults={"author": "Taylor"})
    report = apply(cfg)
    assert report.output == out and not report.missing

    (row,) = markups(out)
    assert row["type"] == "Highlight" and row["color"] == "#A5D6A7" and row["opacity"] == 0.4
    assert row["comment"] == "R2.3" and row["author"] == "Taylor" and row["id"].startswith(NM_PREFIX)
    assert row["text"].split() == TARGET.split()

    # An independent parser sees a complete, standard markup annotation.
    reader = PdfReader(out, strict=True)
    annots = [a.get_object() for a in reader.pages[0]["/Annots"]]
    hl = next(a for a in annots if a["/Subtype"] == "/Highlight")
    lines = report.results[0].placed[0].lines
    assert lines >= 2 and len(hl["/QuadPoints"]) == 8 * lines
    assert hl["/AP"]["/N"].get_object().get_data()  # appearance stream, so every viewer draws it
    assert hl["/T"] == "Taylor" and hl["/Contents"] == "R2.3" and "/M" in hl and "/CreationDate" in hl
    popup = hl["/Popup"].get_object()
    assert popup["/Subtype"] == "/Popup" and popup["/Parent"].get_object()["/NM"] == hl["/NM"]


@pytest.mark.parametrize("kind, subtype", [("underline", "Underline"), ("strikeout", "StrikeOut"), ("squiggly", "Squiggly")])
def test_other_markup_types(make_pdf, config_for, tmp_path, kind, subtype):
    out = tmp_path / "out.pdf"
    apply(config_for(make_pdf(LOREM), [{"text": "hardest one", "type": kind}], out))
    assert markups(out)[0]["type"] == subtype


def test_rerun_replaces_instead_of_duplicating(make_pdf, config_for, tmp_path):
    pdf = make_pdf(LOREM)
    annotations = [{"text": TARGET, "comment": "x"}, {"text": "hardest one"}]
    first = tmp_path / "a.pdf"
    apply(config_for(pdf, annotations, first))
    again = tmp_path / "b.pdf"
    report = apply(config_for(first, annotations, again))
    assert report.removed == 2 and len(markups(again)) == 2
    kept = tmp_path / "c.pdf"
    apply(config_for(first, annotations, kept, remove_existing=False))
    assert len(markups(kept)) == 4


def test_foreign_annotations_are_kept(make_pdf, config_for, tmp_path):
    pdf = make_pdf(LOREM)
    with pymupdf.open(pdf) as doc:
        doc[0].add_text_annot((300, 300), "someone else's note")
        doc.saveIncr()
    out = tmp_path / "out.pdf"
    apply(config_for(pdf, [{"text": "hardest one"}], out))
    with pymupdf.open(out) as doc:
        assert any(r["comment"] == "someone else's note" for r in list_annots(doc))


def test_popup_options_and_sticky_note(make_pdf, config_for, tmp_path):
    out = tmp_path / "out.pdf"
    apply(
        config_for(
            make_pdf(LOREM),
            [
                {"text": "hardest one", "comment": "open popup", "popup": "open"},
                {"text": "proposed method is also fast", "comment": "no popup", "popup": "none"},
                {"text": "final results", "comment": "with icon", "sticky_note": True},
            ],
            out,
        )
    )
    with pymupdf.open(out) as doc:
        page = doc[0]
        by_comment = {a.info["content"]: a for a in page.annots() if a.type[1] == "Highlight"}
        assert by_comment["open popup"].has_popup and by_comment["open popup"].is_open
        assert not by_comment["no popup"].has_popup
        notes = [a for a in page.annots() if a.type[1] == "Text"]
        assert len(notes) == 1 and notes[0].info["content"] == "with icon" and notes[0].info["id"].startswith(NM_PREFIX)
        assert page.rect.contains(notes[0].rect)


def test_comment_on_first_page_only_for_cross_page_match(make_pdf, config_for, tmp_path):
    pdf = make_pdf("Intro text. It ends here", "and continues on the next page.")
    out = tmp_path / "out.pdf"
    apply(config_for(pdf, [{"text": "it ends here and continues on the next page", "comment": "spans pages"}], out))
    rows = markups(out)
    assert [(r["page"], r["comment"]) for r in rows] == [(1, "spans pages"), (2, None)]
    apply(config_for(pdf, [{"text": "it ends here and continues on the next page", "comment": "c", "continuation_comment": "(cont.)"}], out))
    assert [r["comment"] for r in markups(out)] == ["c", "(cont.)"]


def test_group_comment_goes_to_first_placed_annotation(make_pdf, config_for, tmp_path):
    out = tmp_path / "out.pdf"
    report = apply(
        config_for(
            make_pdf(LOREM),
            [
                {"text": "this text is not in the pdf", "comment": "group note", "group": "g"},
                {"text": "hardest one", "group": "g"},
                {"text": "proposed method is also fast", "group": "g"},
            ],
            out,
        )
    )
    assert report.results[0].status == "missing"
    assert [r["comment"] for r in markups(out)] == ["group note", None]


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_rotated_pages(make_pdf, config_for, tmp_path, rotation):
    out = tmp_path / "out.pdf"
    apply(config_for(make_pdf(LOREM, rotation=rotation), [{"text": TARGET, "comment": "r", "sticky_note": True}], out))
    with pymupdf.open(out) as doc:
        page = doc[0]
        unrotated = (page.rect * page.derotation_matrix).normalize()
        (row,) = [r for r in list_annots(doc) if r["type"] == "Highlight"]
        assert row["text"].split() == TARGET.split()
        for a in page.annots():
            if a.type[1] in ("Highlight", "Text"):
                assert unrotated.contains(a.rect)
                if a.has_popup:
                    assert page.rect.contains(a.popup_rect * page.rotation_matrix)


def test_in_place_save_is_incremental(make_pdf, config_for):
    pdf = make_pdf(LOREM)
    size = pdf.stat().st_size
    with pdf.open("rb") as f:
        head = f.read(size)
    apply(config_for(pdf, [{"text": "hardest one"}], pdf))
    data = pdf.read_bytes()
    assert data.startswith(head) and len(data) > size  # original bytes untouched, update appended
    assert len(markups(pdf)) == 1


def test_default_output_and_dry_run(make_pdf, config_for):
    pdf = make_pdf(LOREM)
    report = apply(config_for(pdf, [{"text": "hardest one"}]), dry_run=True)
    assert report.output is None and not default_output(pdf).exists()
    report = apply(config_for(pdf, [{"text": "hardest one"}]))
    assert report.output == default_output(pdf) and report.output.exists()


def test_encrypted_input_needs_password(make_pdf, config_for, tmp_path):
    pdf = make_pdf(LOREM)
    locked = tmp_path / "locked.pdf"
    with pymupdf.open(pdf) as doc:
        doc.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="owner")
    with pytest.raises(ConfigError, match="encrypted"):
        apply(config_for(locked, [{"text": "hardest one"}], tmp_path / "o.pdf"))
    report = apply(config_for(locked, [{"text": "hardest one"}], tmp_path / "o.pdf", password="pw"))
    assert not report.missing
