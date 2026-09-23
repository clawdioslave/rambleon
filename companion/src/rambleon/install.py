"""Install the AddOn into WoW: a symlink by default (live edits), a copy on request."""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

import re

from .paths import ADDON_NAME, Paths, bundled_addon


def _toc_version(folder: Path) -> str:
    toc = folder / f"{ADDON_NAME}.toc"
    try:
        m = re.search(r"^## Version:\s*(\S+)", toc.read_text(errors="replace"), re.M)
        return m.group(1) if m else "0"
    except OSError:
        return "0"


def _version_key(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))


def ensure_addon_source(paths: Paths) -> str | None:
    """Without a checkout, seed (or upgrade) ~/Rambleon/addon/Rambleon from the AddOn bundled in the package.
    Generated files (Chapters.lua) are preserved. Returns a message when something was copied."""
    dest = paths.addon_src
    bundled = bundled_addon()
    if bundled is None or bundled.resolve() == dest.resolve():
        return None
    if (dest / f"{ADDON_NAME}.toc").exists() and _version_key(_toc_version(dest)) >= _version_key(_toc_version(bundled)):
        return None
    dest.mkdir(parents=True, exist_ok=True)
    for src in bundled.iterdir():
        if src.is_file():
            shutil.copy2(src, dest / src.name)
    return f"AddOn {_toc_version(bundled)} unpacked to {dest}"


def link_status(paths: Paths) -> tuple[str, str]:
    """(state, detail) where state in linked | copied | missing | broken | foreign | no-wow."""
    dest = paths.addon_install
    if dest is None:
        return "no-wow", "WoW directory not found"
    if dest.is_symlink():
        target = Path(os.readlink(dest))
        if not dest.exists():
            return "broken", f"symlink points to missing {target}"
        if target.resolve() == paths.addon_src.resolve():
            return "linked", f"{dest} → {target}"
        return "foreign", f"symlink points elsewhere: {target}"
    if dest.is_dir():
        if (dest / f"{ADDON_NAME}.toc").exists():
            src_toc = (paths.addon_src / f"{ADDON_NAME}.toc").read_text(errors="replace")
            dst_toc = (dest / f"{ADDON_NAME}.toc").read_text(errors="replace")
            return "copied", f"real directory at {dest}" + ("" if src_toc == dst_toc else " (out of date)")
        return "foreign", f"directory without a TOC at {dest}"
    return "missing", f"nothing at {dest}"


def install_addon(paths: Paths, copy: bool = False) -> str:
    if paths.wow_dir is None or paths.addons_dir is None or paths.addon_install is None:
        raise RuntimeError("WoW directory not found (set RAMBLEON_WOW_DIR)")
    seeded = ensure_addon_source(paths)
    if not (paths.addon_src / f"{ADDON_NAME}.toc").exists():
        raise RuntimeError(f"AddOn source missing at {paths.addon_src}")
    paths.addons_dir.mkdir(parents=True, exist_ok=True)
    dest = paths.addon_install
    state, _ = link_status(paths)
    if not copy and state == "linked":
        return (seeded + "; " if seeded else "") + f"already linked: {dest} → {paths.addon_src}"
    if dest.is_symlink():
        dest.unlink()
    elif dest.is_dir():
        if copy:
            shutil.rmtree(dest)
        else:
            backup = dest.with_name(f"{dest.name}.replaced-{datetime.now():%Y%m%d%H%M%S}")
            dest.rename(backup)
    if copy:
        shutil.copytree(paths.addon_src, dest, ignore=shutil.ignore_patterns(".DS_Store"))
        return f"copied {paths.addon_src} → {dest}"
    os.symlink(paths.addon_src, dest)
    return (seeded + "; " if seeded else "") + f"linked {dest} → {paths.addon_src}"
