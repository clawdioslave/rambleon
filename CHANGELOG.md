# Changelog

## 0.2.0 — 2026-09-22

- The log just runs: no END CHAPTER. Logging out is the save; `/ramble save` is an optional flush.
- A chapter is a night: every session of one evening stitched together (`ramble nights`, `ramble export tonight`).
- Chapters published back into the game: `/ramble chapters` with selectable text.
- HTML story pages with screenshots, plus an index page (`ramble page tonight`).
- Background watcher as a launchd service (`ramble service install`); chapter written the moment you log out.
- `ramble setup` (one command), `ramble doctor --fix`, `ramble uninstall`, `ramble reprocess`.
- Kills (from the experience chat line), XP, quest objective completions, uncommon-or-better loot and equips.
- Journal voices (`golden`, `field-journal`); character gender recorded; names only from the evidence.
- The companion package now carries the AddOn, so it installs without a checkout.
- MIT license; public repository.

## 0.1.0 — 2026-09-21

- First playable: AddOn loads on WoW: Forever (Interface 16001), `/ramble` panel, session and event model,
  notes and marks, SavedVariables watcher, immutable archive, Markdown export, AI prompt and Claude CLI adapter.
