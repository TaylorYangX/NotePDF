import pytest

from notepdf.tex.detex import Detexer, literal_length


def detex(source, **kw):
    res = Detexer(**kw).run(source, 0, len(source))
    return [(s.kind, s.text) for s in res.segments], [what for _, what in res.skipped]


@pytest.mark.parametrize(
    "source, expected",
    [
        ("We use \\emph{fast} and \\textbf{\\textit{bold}} text.", "We use fast and bold text."),
        ("Prior work~\\cite{a,b} shows", "Prior work {{gap:80}} shows"),
        ("see Fig.~\\ref{f} and \\eqref{e}", "see Fig. {{gap:40}} and {{gap:40}}"),
        ("runs in $\\mathcal{O}(n)$ time", "runs in {{gap:20}} time"),
        ("inline \\(x+y\\) math", "inline {{gap:9}} math"),
        ("na\\\"ive caf\\'{e} fa\\c{c}ade \\ss", "naive cafe facade ß"),
        ("``quoted'' -- and --- dashes", '"quoted" - and - dashes'),
        ("50\\% of A\\&B, e.g.\\ this", "50% of A&B, e.g. this"),
        ("\\href{http://x}{the link} and \\url{http://y}", "the link and {{gap:60}}"),
        ("\\label{x}\\noindent Text \\vspace{2pt}here", "Text here"),
        ("\\unknownmacro{kept text} and \\twoargs{a}{b} end", "kept text and {{gap:8}} end"),
        ("\\textcolor{red}{red words} \\color{blue} rest", "red words rest"),
        ("\\SI{3}{\\meter} long", "{{gap:20}} long"),
    ],
)
def test_inline_conversion(source, expected):
    segments, _ = detex(source)
    assert segments == [("text", expected)]


def test_segments_split_at_structure():
    source = (
        "First paragraph.\n\nSecond paragraph.\\par Third.\n"
        "\\section{A Heading}\n"
        "\\begin{itemize}\\item one item \\item[(b)] two item\\end{itemize}"
    )
    segments, _ = detex(source)
    assert segments == [
        ("text", "First paragraph."),
        ("text", "Second paragraph."),
        ("text", "Third."),
        ("heading", "A Heading"),
        ("text", "one item"),
        ("text", "(b) two item"),
    ]


def test_display_math_and_floats_are_reported():
    source = (
        "Before.\n\\begin{equation}\n y = f(x)\n\\end{equation}\nAfter \\[ z \\] and $$ w $$ end."
        "\\begin{figure}[t]\\includegraphics{a}\\caption{A caption.}\\end{figure}"
        "\\begin{tabular}{cc} a & b \\end{tabular}"
    )
    segments, skipped = detex(source)
    assert segments == [("text", "Before."), ("text", "After"), ("text", "and"), ("text", "end."), ("caption", "A caption.")]
    assert skipped == [
        "display math (equation) is not highlighted",
        "display math (\\[...\\]) is not highlighted",
        "display math ($$) is not highlighted",
        "figure contents are not highlighted (its caption is)",
        "tabular environment is not highlighted",
    ]


def test_footnotes_and_captions_are_separate_segments():
    segments, _ = detex("Main text\\footnote{The note.} continues.")
    assert segments == [("text", "Main text{{gap:4}} continues."), ("footnote", "The note.")]
    segments, _ = detex("Main text\\footnote{The note.} continues.", include_footnotes=False)
    assert segments == [("text", "Main text{{gap:4}} continues.")]
    segments, _ = detex("\\begin{figure}\\caption{Cap.}\\end{figure}", include_captions=False)
    assert segments == []


def test_macro_expansion_and_replacements():
    segments, _ = detex("We propose \\ours{} and \\tool.", text_macros={"ours": "OurNet\\xspace"}, replacements={"\\tool": "ToolKit"})
    assert segments == [("text", "We propose OurNet and ToolKit.")]


def test_literal_length():
    assert literal_length("a {{gap:40}} bc.") == 3
