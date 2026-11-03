"""Compile examples/paper with pdflatex and highlight its revisions. Skipped when pdflatex isn't installed."""

import shutil
import subprocess
from pathlib import Path

import pymupdf
import pytest

from notepdf.apply import apply
from notepdf.config import Config

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")


@pytest.mark.parametrize("build", ["review", "clean"])
def test_example_paper(tmp_path, build):
    shutil.copytree(EXAMPLES / "paper", tmp_path / "paper")
    shutil.copy(EXAMPLES / "tex_config.yaml", tmp_path / "tex_config.yaml")
    tex = tmp_path / "paper" / "paper.tex"
    if build == "clean":  # revised text rendered in black: matching must not depend on color
        tex.write_text(tex.read_text().replace(r"\definecolor{revcolor}{RGB}{0,0,200}", r"\definecolor{revcolor}{RGB}{0,0,0}"))
    for _ in range(2):  # second run resolves \ref
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "paper.tex"],
            cwd=tmp_path / "paper", check=True, capture_output=True, timeout=120,
        )

    report = apply(Config.load(tmp_path / "tex_config.yaml"))
    assert [r.entry.label for r in report.missing] == []
    assert any("display math (equation)" in n for n in report.notes)

    with pymupdf.open(report.output) as doc:
        notes = {a.info["content"] for page in doc for a in page.annots() if a.type[1] == "Highlight"}
    assert {"R1.1 -- clarified the motivation", "R2.3 -- new evaluation", "R3.2 -- explain the matching step", "R1.4 -- added limitations"} <= notes
    assert any(n.startswith("Revised (method.tex:") for n in notes)  # template comment for the marker without %@note
