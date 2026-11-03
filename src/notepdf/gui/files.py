"""File access for the GUI: folder listings, Windows paths under WSL, and opening files in their default app."""

from __future__ import annotations

import functools
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

WINDOWS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
EXPLORER = "/mnt/c/Windows/explorer.exe"


@functools.cache
def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def normalize_path(raw: str) -> Path:
    """A path as typed or pasted: quotes stripped, ``~`` expanded, Windows paths converted under WSL."""
    text = raw.strip().strip('"').strip("'").strip()
    if not text:
        raise ValueError("empty path")
    if WINDOWS_PATH_RE.match(text) and is_wsl():
        out = subprocess.run(["wslpath", "-u", text], capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            raise ValueError(out.stderr.strip() or f"can't convert {text!r}")
        return Path(out.stdout.strip())
    return Path(text).expanduser()


SYSTEM_USERS = {"Public", "Default", "Default User", "All Users", "WDAGUtilityAccount"}


@functools.cache
def windows_home() -> Optional[Path]:
    """The Windows user folder under WSL, if there's an unambiguous one."""
    users = Path("/mnt/c/Users")
    if not users.is_dir():
        return None
    same_name = users / os.environ.get("USER", "")
    if same_name.is_dir():
        return same_name
    try:
        candidates = [p for p in users.iterdir() if p.name not in SYSTEM_USERS and (p / "Desktop").is_dir()]
    except OSError:
        return None
    return candidates[0] if len(candidates) == 1 else None


def roots() -> list[dict]:
    """Shortcuts for the file dialog."""
    out = [{"name": "home", "path": str(Path.home())}]
    win = windows_home()
    if win is not None:
        out += [{"name": f"windows_{d.lower()}", "path": str(win / d)} for d in ("Desktop", "Documents", "Downloads") if (win / d).is_dir()]
    if Path("/mnt/c").is_dir():
        out.append({"name": "windows_c", "path": "/mnt/c"})
    out.append({"name": "root", "path": "/"})
    return out


def list_dir(path: Path, extensions: Optional[list[str]] = None, show_hidden: bool = False) -> dict:
    path = path.expanduser()
    if path.is_file():
        path = path.parent
    if not path.is_dir():
        raise FileNotFoundError(f"{path} is not a folder")
    exts = {e.lower().lstrip(".") for e in extensions or []}
    entries = []
    try:
        children = list(path.iterdir())
    except PermissionError as e:
        raise PermissionError(f"can't read {path}") from e
    for child in children:
        if not show_hidden and child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
            if not is_dir and exts and child.suffix.lower().lstrip(".") not in exts:
                continue
            stat = child.stat()
        except OSError:
            continue
        entries.append(
            {"name": child.name, "path": str(child), "kind": "dir" if is_dir else "file", "size": None if is_dir else stat.st_size, "mtime": stat.st_mtime}
        )
    entries.sort(key=lambda e: (e["kind"] != "dir", e["name"].lower()))
    parent = str(path.parent) if path.parent != path else None
    return {"path": str(path), "parent": parent, "entries": entries, "roots": roots()}


def windows_path(path: Path) -> str:
    out = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, timeout=10)
    if out.returncode != 0:
        raise ValueError(out.stderr.strip() or f"can't convert {path}")
    return out.stdout.strip()


def open_with_default_app(path: Path, reveal: bool = False) -> None:
    """Open a file (or show it in its folder). Under WSL this goes through Windows Explorer."""
    if not path.exists():
        raise FileNotFoundError(f"{path} doesn't exist")
    if is_wsl():
        explorer = EXPLORER if Path(EXPLORER).exists() else "explorer.exe"
        arg = f"/select,{windows_path(path)}" if reveal else windows_path(path)
        subprocess.Popen([explorer, arg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        target = path.parent if reveal and path.is_file() else path
        subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_url(url: str) -> None:
    """Open the GUI in the user's browser (the Windows one under WSL)."""
    if is_wsl():
        explorer = EXPLORER if Path(EXPLORER).exists() else "explorer.exe"
        subprocess.Popen([explorer, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    import webbrowser

    webbrowser.open(url)
