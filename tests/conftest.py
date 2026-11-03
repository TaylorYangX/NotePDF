from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import pymupdf
import pytest

from notepdf.config import Config


def build_pdf(path: Path, pages: list[str], rotation: int = 0, width: float = 230) -> Path:
    """One page per HTML snippet, laid out in a narrow box so sentences wrap over several lines."""
    doc = pymupdf.open()
    for html in pages:
        page = doc.new_page()
        page.insert_htmlbox(pymupdf.Rect(72, 72, 72 + width, 770), f"<div style='font-size:11pt'>{html}</div>")
        if rotation:
            page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    def make(*pages: str, name: str = "in.pdf", rotation: int = 0, width: float = 230) -> Path:
        return build_pdf(tmp_path / name, list(pages), rotation=rotation, width=width)

    return make


@pytest.fixture
def config_for() -> Callable[..., Config]:
    def make(pdf: Path, annotations: list[dict], output: Optional[Path] = None, **top) -> Config:
        data = {"input": str(pdf), "annotations": annotations, **top}
        if output is not None:
            data["output"] = str(output)
        return Config.model_validate(data)

    return make


LOREM = (
    "The final results show that our proposed method significantly outperforms the baseline on every "
    "benchmark we tried, including the hardest one. Our proposed method is also fast."
)
