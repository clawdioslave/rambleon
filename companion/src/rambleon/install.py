"""Install the AddOn into WoW: a symlink by default (live edits), a copy on request."""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from .paths import ADDON_NAME, Paths


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
    if not (paths.addon_src / f"{ADDON_NAME}.toc").exists():
        raise RuntimeError(f"AddOn source missing at {paths.addon_src}")
    paths.addons_dir.mkdir(parents=True, exist_ok=True)
    dest = paths.addon_install
    state, _ = link_status(paths)
    if not copy and state == "linked":
        return f"already linked: {dest} → {paths.addon_src}"
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
    return f"linked {dest} → {paths.addon_src}"
