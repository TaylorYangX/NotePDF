import textwrap

import pytest

from notepdf.config import MarkerSpec
from notepdf.tex.markers import find_markers
from notepdf.tex.reader import read_tex

PREAMBLE = "\\documentclass{article}\n\\usepackage{xcolor}\n\\definecolor{revcolor}{RGB}{0,0,255}\n"


def tex(tmp_path, body, preamble=PREAMBLE, name="main.tex"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(preamble) + "\\begin{document}\n" + textwrap.dedent(body) + "\n\\end{document}\n")
    return read_tex(path)


def bodies(src, specs=None, **kw):
    return [src.text[m.body_start : m.body_end].strip() for m in find_markers(src, specs or [MarkerSpec(color="revcolor")], **kw)]


def test_comments_are_stripped_like_tex(tmp_path):
    src = tex(tmp_path, "50\\% done % a comment\nfoo%\n   bar\n")
    body = src.text[src.body_start : src.body_end]
    assert "50\\% done " in body and "a comment" not in body and "foobar" in body


def test_input_is_inlined_with_source_map(tmp_path):
    (tmp_path / "sec").mkdir()
    (tmp_path / "sec" / "intro.tex").write_text("line one\n{\\color{revcolor} inside the include}\n")
    src = tex(tmp_path, "before\n\\input{sec/intro}\nafter\n")
    (mk,) = find_markers(src, [MarkerSpec(color="revcolor")])
    assert src.source_ref(mk.start) == "sec/intro.tex:2"
    assert src.text.index("before") < src.text.index("line one") < src.text.index("after")


def test_ignored_regions(tmp_path):
    src = tex(
        tmp_path,
        """\
        % {\\color{revcolor} commented}
        \\iffalse {\\color{revcolor} hidden \\ifx a b \\fi still hidden} \\fi
        \\begin{comment}{\\color{revcolor} in comment env}\\end{comment}
        {\\color{revcolor} visible}
        """,
    )
    assert bodies(src) == ["visible"]


@pytest.mark.parametrize(
    "body, expected",
    [
        ("a {\\color{revcolor} one {two} three} b", ["one {two} three"]),
        ("{\\color{revcolor} first}{\\color{revcolor} second}", ["first", "second"]),
        ("\\textcolor{revcolor}{arg text} after", ["arg text"]),
        ("\\begingroup\\color{revcolor} grouped\\endgroup after", ["grouped"]),
        ("\\color{revcolor} switched on \\color{black} off", ["switched on"]),
        ("\\begin{itemize}\\item \\color{revcolor} item one \\item item two\\end{itemize} out", ["item one \\item item two"]),
        ("{\\color{revcolor} outer \\textcolor{revcolor}{nested} end}", ["outer \\textcolor{revcolor}{nested} end"]),
        ("{\\color{revcolor} has \\} brace}", ["has \\} brace"]),
    ],
)
def test_color_scopes(tmp_path, body, expected):
    assert bodies(tex(tmp_path, body)) == expected


def test_macro_and_env_markers(tmp_path):
    src = tex(tmp_path, "\\rev[R1]{macro text} and \\begin{revised}[opt] env text \\end{revised}")
    specs = [MarkerSpec(macro="rev"), MarkerSpec(env="revised")]
    assert bodies(src, specs) == ["macro text", "env text"]


def test_wrapper_macros_are_detected(tmp_path):
    preamble = PREAMBLE + "\\newcommand{\\rev}[1]{{\\color{revcolor}#1}}\n\\newcommand{\\revopt}[2][]{\\textcolor{revcolor}{#2}}\n"
    src = tex(tmp_path, "\\rev{one} and \\revopt[x]{two}", preamble=preamble)
    markers = find_markers(src, [MarkerSpec(color="revcolor", highlight="green")])
    assert [(m.kind, m.name, src.text[m.body_start : m.body_end]) for m in markers] == [("macro", "rev", "one"), ("macro", "revopt", "two")]
    assert all(m.spec.highlight == "green" and m.tex_color == (0, 0, 1) for m in markers)
    assert bodies(src, detect_macros=False) == []


def test_colors_from_preamble(tmp_path):
    preamble = (
        "\\definecolor{a}{rgb}{1,0,0}\\definecolor{b}{HTML}{00FF00}\\definecolor{c}{gray}{0.5}"
        "\\definecolor{d}{cmyk}{0,1,1,0}\\colorlet{e}{b}\n"
    )
    src = tex(tmp_path, "x", preamble=preamble)
    assert src.colors["a"] == (1, 0, 0) and src.colors["b"] == (0, 1, 0) and src.colors["c"] == (0.5, 0.5, 0.5)
    assert src.colors["d"] == (1, 0, 0) and src.colors["e"] == (0, 1, 0) and src.colors["blue"] == (0, 0, 1)


def test_text_macros(tmp_path):
    preamble = PREAMBLE + "\\newcommand{\\ours}{OurNet\\xspace}\n\\def\\eg{e.g.}\n\\newcommand{\\withargs}[1]{x#1}\n"
    src = tex(tmp_path, "x", preamble=preamble)
    assert src.text_macros == {"ours": "OurNet\\xspace", "eg": "e.g."}


def test_notes(tmp_path):
    src = tex(
        tmp_path,
        """\
        {\\color{revcolor} %@note: inside the marker
        first}
        %@note: on the line above
        %@note: second line of the same note
        \\textcolor{revcolor}{second}
        %@note: line above, marker mid-line
        Some text, then \\textcolor{revcolor}{third}
        %@note: orphan

        {\\color{revcolor} fourth}
        """,
    )
    assert [m.note for m in find_markers(src, [MarkerSpec(color="revcolor")])] == [
        "inside the marker",
        "on the line above\nsecond line of the same note",
        "line above, marker mid-line",
        None,
    ]
