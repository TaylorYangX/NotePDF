"""Warnings and notes that read as plain English strings but also carry a code for translation."""

from __future__ import annotations

from typing import Any


class Msg(str):
    """A ``str`` (the English text, used by the CLI) plus ``code`` and ``params`` (used by the GUI)."""

    code: str
    params: dict[str, Any]

    def __new__(cls, code: str, text: str, **params: Any) -> "Msg":
        obj = super().__new__(cls, text)
        obj.code = code
        obj.params = params
        return obj

    def with_source(self, source: str) -> "Msg":
        """The same message prefixed with a ``file.tex:line`` reference."""
        return Msg(self.code, f"{source}: {self}", **self.params, source=source)


def msg_dict(message: str) -> dict[str, Any]:
    if isinstance(message, Msg):
        return {"code": message.code, "params": message.params, "text": str(message)}
    return {"code": None, "params": {}, "text": str(message)}
