import json
import subprocess
import textwrap

import pymupdf
import pytest
import yaml

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from notepdf.gui import files  # noqa: E402
from notepdf.gui.server import LOCAL_HOSTS, create_app  # noqa: E402
from notepdf.gui.session import SESSION  # noqa: E402

from .conftest import LOREM, build_pdf  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    SESSION.current = None
    yield
    SESSION.current = None


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def pdf(tmp_path):
    return build_pdf(tmp_path / "doc.pdf", [LOREM + " Our proposed method wins.", "Our proposed method again."])


def config(pdf, *annotations, **top):
    return {"input": str(pdf), "annotations": list(annotations), **top}


def test_meta_and_settings(client, tmp_path):
    meta = client.get("/api/meta").json()
    assert meta["version"] and meta["app_mode"] is False and meta["initial"] is None
    assert client.get("/api/settings").json()["theme"] == "system"
    assert client.put("/api/settings", json={"language": "zh-CN", "theme": "dark"}).json()["language"] == "zh-CN"
    saved = json.loads((tmp_path / "xdg" / "notepdf" / "gui.json").read_text())
    assert saved["language"] == "zh-CN" and saved["theme"] == "dark"
    assert client.put("/api/settings", json={"theme": "neon"}).status_code == 422


def test_initial_file_is_reported(tmp_path, pdf):
    meta = TestClient(create_app(initial=str(pdf))).get("/api/meta").json()
    assert meta["initial"] == {"path": str(pdf.resolve()), "kind": "pdf"}


def test_foreign_host_is_rejected():
    client = TestClient(create_app(LOCAL_HOSTS), base_url="http://127.0.0.1")
    assert client.get("/api/meta").status_code == 200
    assert client.get("/api/meta", headers={"host": "evil.example"}).status_code == 400


def test_fs_listing(client, tmp_path, pdf):
    (tmp_path / "sub").mkdir()
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / ".hidden.pdf").write_text("x")
    data = client.get("/api/fs", params={"path": str(tmp_path), "ext": "pdf"}).json()
    assert [(e["name"], e["kind"]) for e in data["entries"]] == [("sub", "dir"), ("doc.pdf", "file")]
    assert data["parent"] == str(tmp_path.parent) and any(r["name"] == "home" for r in data["roots"])
    assert client.get("/api/fs", params={"path": str(tmp_path / "missing")}).status_code == 404


def test_windows_paths_are_converted(client, monkeypatch):
    monkeypatch.setattr(files, "is_wsl", lambda: True)

    def fake_run(cmd, **kw):
        assert cmd[:2] == ["wslpath", "-u"]
        return subprocess.CompletedProcess(cmd, 0, stdout="/mnt/c/Users/me/paper.pdf\n", stderr="")

    monkeypatch.setattr(files.subprocess, "run", fake_run)
    data = client.post("/api/path/normalize", json={"path": '"C:\\Users\\me\\paper.pdf"'}).json()
    assert data["path"] == "/mnt/c/Users/me/paper.pdf" and data["exists"] is False


def test_open_render_and_words(client, pdf):
    info = client.post("/api/pdf/open", json={"path": str(pdf)}).json()
    assert info["name"] == "doc.pdf" and len(info["pages"]) == 2 and info["existing"] == 0
    png = client.get("/api/pdf/page/0.png", params={"scale": 1}).content
    pix = pymupdf.Pixmap(png)
    assert (pix.width, pix.height) == (round(info["pages"][0]["width"]), round(info["pages"][0]["height"]))
    words = client.get("/api/pdf/page/0/words").json()["words"]
    assert words[0]["text"] == "The" and len(words[0]["rect"]) == 4
    assert client.get("/api/pdf/page/9.png").status_code == 404
    recent = client.get("/api/settings").json()["recent"]
    assert recent[0]["kind"] == "pdf" and recent[0]["path"] == str(pdf.resolve())


def test_existing_notepdf_annotations_are_hidden_from_render(client, pdf, tmp_path):
    out = tmp_path / "annotated.pdf"
    client.post("/api/apply", json={"config": config(pdf, {"text": "hardest one"}), "output": str(out)})
    info = client.post("/api/pdf/open", json={"path": str(out)}).json()
    assert info["existing"] == 1
    assert len(list(SESSION.current.render_doc[0].annots())) == 0


def test_preview_statuses_and_rects(client, pdf):
    cfg = config(
        pdf,
        {"text": "significantly outperforms the baseline", "comment": "c"},
        {"text": "our proposed method", "occurrence": "all"},
        {"text": "not in this document"},
        {"text": "x", "color": "nope"},
        {"text": "our proposed method", "occurrence": 9},
    )
    data = client.post("/api/preview", json={"config": cfg}).json()
    statuses = [e["status"] for e in data["entries"]]
    assert statuses == ["found", "found", "missing", "invalid", "missing"]
    assert data["counts"] == {"found": 2, "warning": 0, "missing": 2, "invalid": 1}
    assert "unknown color" in data["entries"][3]["error"]
    assert data["entries"][4]["warnings"][0]["code"] == "occurrence_missing"
    hits = data["entries"][1]["hits"]
    assert sorted({h["page"] for h in hits}) == [0, 1]
    x0, y0, x1, y1 = data["entries"][0]["hits"][0]["rects"][0]
    assert x1 > x0 and y1 > y0


def test_preview_rects_follow_page_rotation(client, tmp_path):
    rotated = build_pdf(tmp_path / "rot.pdf", [LOREM], rotation=90)
    data = client.post("/api/preview", json={"config": config(rotated, {"text": "hardest one"})}).json()
    x0, y0, x1, y1 = data["entries"][0]["hits"][0]["rects"][0]
    page = client.post("/api/pdf/open", json={"path": str(rotated)}).json()["pages"][0]
    assert page["width"] > page["height"]  # landscape view of a portrait page
    assert 0 <= x0 < x1 <= page["width"] and 0 <= y0 < y1 <= page["height"]
    assert (y1 - y0) > (x1 - x0)  # rotated text: the box is tall, not wide


def test_bad_document_settings(client, pdf):
    resp = client.post("/api/preview", json={"config": config(pdf, defaults={"opacity": 3})})
    assert resp.status_code == 422 and "opacity" in resp.json()["detail"]


def test_selection_targets_the_dragged_occurrence(client, tmp_path):
    doc = build_pdf(tmp_path / "rep.pdf", ["alpha beta. gamma alpha beta. delta.", "alpha beta again."])
    client.post("/api/pdf/open", json={"path": str(doc)})
    words = [w["text"] for w in client.get("/api/pdf/page/0/words").json()["words"]]
    second = [i for i, w in enumerate(words) if w == "alpha"][1]
    sug = client.post("/api/pdf/selection", json={"page": 0, "first": second, "last": second + 1}).json()
    assert sug["text"] == "alpha beta." and sug["pages"] == 1 and sug["occurrence"] == 2 and sug["matches"] == 3
    # the suggestion really highlights that occurrence
    data = client.post("/api/preview", json={"config": config(doc, {k: sug[k] for k in ("text", "pages", "occurrence")})}).json()
    (hit,) = data["entries"][0]["hits"]
    word_rects = client.get("/api/pdf/page/0/words").json()["words"]
    assert abs(hit["rects"][0][0] - word_rects[second]["rect"][0]) < 2

    unique = client.post("/api/pdf/selection", json={"page": 0, "first": len(words) - 1, "last": len(words) - 1}).json()
    assert unique == {"text": "delta.", "matches": 1}


def test_apply_writes_pdf(client, pdf, tmp_path):
    out = tmp_path / "out.pdf"
    cfg = config(pdf, {"text": "hardest one", "comment": "R1", "color": "#A5D6A7"}, {"text": "missing words here"}, defaults={"author": "GUI"})
    data = client.post("/api/apply", json={"config": cfg, "output": str(out)}).json()
    assert data["output"] == str(out) and [e["status"] for e in data["entries"]] == ["found", "missing"]
    with pymupdf.open(out) as doc:
        (a,) = [a for a in doc[0].annots() if a.type[1] == "Highlight"]
        assert a.info["content"] == "R1" and a.info["title"] == "GUI"
    bad = client.post("/api/apply", json={"config": config(pdf, {"text": "x", "pages": "0"})})
    assert bad.status_code == 422 and "#1" in bad.json()["detail"]


def test_config_save_and_load_round_trip(client, pdf, tmp_path):
    folder = tmp_path / "cfg"
    folder.mkdir()
    cfg = config(pdf, {"text": "hardest one", "comment": "", "pages": [], "color": "pink"}, output=str(tmp_path / "o.pdf"), defaults={"author": "Me"})
    saved = client.post("/api/config/save", json={"path": str(folder / "mine"), "config": cfg}).json()
    assert saved["path"].endswith("mine.yaml")
    on_disk = yaml.safe_load((folder / "mine.yaml").read_text())
    assert on_disk["input"] == "../doc.pdf"  # relative to the config, so they can move together
    assert on_disk["annotations"] == [{"text": "hardest one", "color": "pink"}]  # empty form fields dropped
    loaded = client.post("/api/config/load", json={"path": str(folder / "mine.yaml")}).json()
    assert loaded["config"]["input"] == str(pdf.resolve()) and loaded["converted"] is False
    assert client.post("/api/config/save", json={"path": str(folder / "x.yaml"), "config": config(pdf, {"regex": "("})}).status_code == 422


TEX = r"""
\documentclass{article}
\usepackage{xcolor}
\definecolor{revcolor}{RGB}{0,0,255}
\begin{document}
{\color{revcolor} %@note: R1 rewritten
The final results show that our proposed method significantly outperforms the baseline.
\begin{equation} y = f(x) \end{equation}}
\end{document}
"""


def test_tex_import(client, tmp_path):
    main = tmp_path / "paper.tex"
    main.write_text(textwrap.dedent(TEX))
    data = client.post("/api/tex/import", json={"tex": {"main": str(main), "markers": [{"color": "revcolor", "highlight": "green"}]}}).json()
    assert data["markers"] == 1 and data["rows"][0]["comment"] == "R1 rewritten" and data["rows"][0]["color"] == "#8BC34A"
    assert data["tex_source"]["main"] == str(main) and data["defaults"]["sequential"] is True
    assert client.post("/api/tex/import", json={"tex": {"main": str(tmp_path / "none.tex")}}).status_code == 404


def test_loading_a_live_tex_config_imports_its_entries(client, tmp_path, pdf):
    (tmp_path / "paper.tex").write_text(textwrap.dedent(TEX))
    (tmp_path / "c.yaml").write_text(f"input: {pdf.name}\ntex:\n  main: paper.tex\n")
    data = client.post("/api/config/load", json={"path": str(tmp_path / "c.yaml")}).json()
    assert data["converted"] is True and "tex" not in data["config"]
    assert data["config"]["tex_source"]["main"] == str(tmp_path / "paper.tex")
    assert len(data["config"]["annotations"]) == 1
    assert any(n["code"] == "skip_display_math" for n in data["notes"])


def test_password_protected_pdf(client, pdf, tmp_path):
    locked = tmp_path / "locked.pdf"
    with pymupdf.open(pdf) as doc:
        doc.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="owner")
    resp = client.post("/api/pdf/open", json={"path": str(locked)})
    assert resp.status_code == 401 and resp.json()["detail"] == "password_required"
    assert client.post("/api/pdf/open", json={"path": str(locked), "password": "pw"}).json()["encrypted"] is True
    assert client.get("/api/pdf/page/0.png").status_code == 200
