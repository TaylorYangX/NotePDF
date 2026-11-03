"""GUI preferences: language, theme and recently used files ($XDG_CONFIG_HOME/notepdf/gui.json)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

MAX_RECENT = 12


class RecentFile(BaseModel):
    path: str
    kind: Literal["pdf", "config", "tex"]
    opened: float = Field(default_factory=time.time)


class GuiSettings(BaseModel):
    language: Optional[Literal["en", "zh-CN"]] = None  # None: follow the browser
    theme: Literal["system", "light", "dark"] = "system"
    recent: list[RecentFile] = Field(default_factory=list)


def settings_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "notepdf" / "gui.json"


def load_settings() -> GuiSettings:
    path = settings_path()
    try:
        return GuiSettings.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return GuiSettings()


def save_settings(settings: GuiSettings) -> GuiSettings:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return settings


def add_recent(path: Path, kind: str) -> None:
    settings = load_settings()
    resolved = str(Path(path).resolve())
    settings.recent = [r for r in settings.recent if r.path != resolved]
    settings.recent.insert(0, RecentFile(path=resolved, kind=kind))  # type: ignore[arg-type]
    settings.recent = settings.recent[:MAX_RECENT]
    save_settings(settings)
