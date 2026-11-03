"""Color parsing: hex strings, names, and RGB lists -> (r, g, b) floats in 0..1."""

from __future__ import annotations

from typing import Sequence, Union

RGB = tuple[float, float, float]
ColorLike = Union[str, Sequence[float]]

# Soft highlighter tones, so text stays readable under a 0.4-opacity Multiply blend.
NAMED_COLORS: dict[str, str] = {
    "yellow": "#FFEB3B",
    "green": "#8BC34A",
    "blue": "#64B5F6",
    "cyan": "#4DD0E1",
    "pink": "#F48FB1",
    "red": "#EF5350",
    "orange": "#FFB74D",
    "purple": "#BA68C8",
    "gray": "#BDBDBD",
    "grey": "#BDBDBD",
    "black": "#000000",
    "white": "#FFFFFF",
}


def parse_color(value: ColorLike) -> RGB:
    """Parse ``"#FFEB3B"``, ``"FFEB3B"``, ``"#FE3"``, ``"yellow"``, ``[1, 0.9, 0.2]`` or ``[255, 235, 59]``."""
    if isinstance(value, str):
        s = value.strip()
        named = NAMED_COLORS.get(s.lower())
        if named:
            s = named
        h = s.lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in h):
            raise ValueError(f"unknown color {value!r}; use a name ({', '.join(NAMED_COLORS)}), '#RRGGBB' or [r, g, b]")
        return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]

    vals = [float(v) for v in value]
    if len(vals) != 3:
        raise ValueError(f"color list must have 3 components, got {value!r}")
    if any(v > 1 for v in vals):
        if any(v < 0 or v > 255 for v in vals):
            raise ValueError(f"RGB components must be 0-255, got {value!r}")
        vals = [v / 255 for v in vals]
    elif any(v < 0 for v in vals):
        raise ValueError(f"RGB components must be 0-1, got {value!r}")
    return (vals[0], vals[1], vals[2])


def to_hex(rgb: RGB) -> str:
    return "#" + "".join(f"{round(c * 255):02X}" for c in rgb)


def from_srgb_int(value: int) -> RGB:
    """Convert PyMuPDF's span color (0xRRGGBB int) to floats."""
    return ((value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255)


def color_distance(a: RGB, b: RGB) -> float:
    return max(abs(x - y) for x, y in zip(a, b))
