import pytest
import yaml

from notepdf.colors import parse_color, to_hex
from notepdf.config import Config, ConfigError, pages_to_indices, parse_pages


def test_parse_color_forms():
    assert to_hex(parse_color("#FFEB3B")) == "#FFEB3B"
    assert to_hex(parse_color("fe3")) == "#FFEE33"
    assert to_hex(parse_color([255, 0, 0])) == "#FF0000"
    assert parse_color([1, 0.5, 0]) == (1.0, 0.5, 0.0)
    assert to_hex(parse_color("Yellow")) == "#FFEB3B"
    with pytest.raises(ValueError):
        parse_color("not-a-color")
    with pytest.raises(ValueError):
        parse_color([1, 2])


def test_parse_pages():
    assert parse_pages(3) == [(3, 3)]
    assert parse_pages([1, "4-5"]) == [(1, 1), (4, 5)]
    assert parse_pages("2, 7-") == [(2, 2), (7, None)]
    assert pages_to_indices(parse_pages("2, 7-"), 8) == [1, 6, 7]
    assert pages_to_indices(None, 3) == [0, 1, 2]
    for bad in ("0", "5-3", "x"):
        with pytest.raises(ValueError):
            parse_pages(bad)


def test_entry_overrides_defaults():
    cfg = Config.model_validate(
        {"defaults": {"color": "green", "author": "T"}, "annotations": [{"text": "a", "opacity": 0.2}, {"regex": "b+"}]}
    )
    first, second = cfg.entries()
    assert first.style.opacity == 0.2 and first.style.author == "T"
    assert second.style.opacity == 0.4 and to_hex(second.style.color) == "#8BC34A"


@pytest.mark.parametrize(
    "entry, message",
    [
        ({"text": "a", "regex": "b"}, "exactly one of 'text' or 'regex'"),
        ({"text": "a", "colour": "red"}, "unknown annotation field"),
        ({"regex": "("}, "invalid regex"),
        ({"text": "a", "pages": "0"}, "1-based"),
    ],
)
def test_invalid_entries(tmp_path, entry, message):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({"annotations": [entry]}))
    with pytest.raises(ConfigError, match=message):
        Config.load(path)


def test_style_error_reports_entry_number(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("annotations:\n  - text: ok\n  - text: bad\n    color: nope\n")
    with pytest.raises(ConfigError, match=r"annotation #2"):
        Config.load(path)


def test_relative_paths_resolve_against_config(tmp_path):
    (tmp_path / "sub").mkdir()
    path = tmp_path / "sub" / "c.yaml"
    path.write_text("input: paper.pdf\ntex:\n  main: paper.tex\n")
    cfg = Config.load(path)
    assert cfg.input == tmp_path / "sub" / "paper.pdf"
    assert cfg.tex.main == tmp_path / "sub" / "paper.tex"
    assert cfg.tex.markers[0].color == "revcolor"


def test_json_config(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"annotations": [{"text": "x", "color": [0, 0, 255]}]}')
    assert to_hex(Config.load(path).entries()[0].style.color) == "#0000FF"
