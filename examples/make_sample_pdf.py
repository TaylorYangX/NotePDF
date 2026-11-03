"""Create examples/sample.pdf, the input used by examples/highlights.yaml."""

from pathlib import Path

import pymupdf

PAGES = [
    """
    <h2>1 Introduction</h2>
    <p>Cyber-physical systems control critical infrastructure such as water treatment facilities,
    power grids and transportation networks. Our proposed method significantly outperforms the
    baseline on every benchmark we tried, including the hardest one.</p>
    <p>Prior work [12, 15] focused on offline detection. In contrast to prior work, our method
    adapts online. Results are summarized in Table 1 and Table 2.</p>
    """,
    """
    <h2>2 Method</h2>
    <p>Our method has two steps. First, the input is encoded with a transformer; second, the
    anomaly score is thresholded automatically. The loss converges after a few epochs.</p>
    <p>A limitation is that our method needs a short warm-up period.</p>
    """,
]


def main() -> None:
    out = Path(__file__).with_name("sample.pdf")
    doc = pymupdf.open()
    for html in PAGES:
        page = doc.new_page()
        page.insert_htmlbox(pymupdf.Rect(72, 72, 523, 770), f"<div style='font-size:11pt'>{html}</div>")
    doc.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
