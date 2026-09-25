"""Optional local overrides: <repo>/rambleon.local.toml (gitignored). Facts the archive does not hold yet."""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .paths import find_repo_root

FILENAME = "rambleon.local.toml"


def load_local_config(repo_root: Path | None = None) -> dict[str, Any]:
    path = (repo_root or find_repo_root()) / FILENAME
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def character_overrides(slug: str, repo_root: Path | None = None) -> dict[str, Any]:
    chars = load_local_config(repo_root).get("characters", {})
    return chars.get(slug, {}) if isinstance(chars, dict) else {}


def share_auto(repo_root: Path | None = None) -> bool:
    """`[share] auto = true`: push every finished chapter to GitHub Pages without asking. Off unless this
    machine's rambleon.local.toml says so; the file is gitignored, so it never travels with the repo."""
    share = load_local_config(repo_root).get("share", {})
    return bool(share.get("auto")) if isinstance(share, dict) else False
