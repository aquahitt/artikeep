# Changelog

## Unreleased

### Added

- Each version keeps the request that led to it (the user's message, up to 500 characters)
  and the session id, for Claude Code publishes and Docs exports and for Codex deliverables.
  The gallery shows it under the version and in the compare view, search finds a version by
  the words of its request, and the MCP `list_versions` tool returns it. `"provenance": false`
  in `artikeep.json` turns it off. Versions saved earlier have none.
- `artikeep restore <id> [--version N] [--to DIR]` and the MCP `restore_artifact` tool copy an
  archived page or canvas out and say how to publish it again, for a dead link, another account,
  or to continue old work. When the agent publishes those files, the new link joins the same
  item as a new version ("republished from vN") instead of creating a duplicate.

## 0.2.1 — 2026-11-18

### Changed

- The README recommends the Claude Code plugin: two `/plugin` commands, nothing to install
  first. The `uv tool` / `pipx` route covers Codex and Claude Desktop.

### Fixed

- Claude Design canvases published in several calls no longer split between `project/` and
  `data/project/` in the archive, which left most boards blank and the page tabs stale
  (#6). Canvases already archived that way are merged on the next background pass, newest
  copy first, in every version too.
- The canvas viewer says when it is a static preview: the Design runtime stays on the host,
  so computed text, theme colors and repeated parts may be missing.
- A page file outside the publish `root` is reported as not saved instead of being copied
  next to the item's folder.

## 0.2.0 — 2026-10-25

### Added

- `artikeep serve`: the gallery as a local app on 127.0.0.1. Full-text search with
  highlighted matches, live updates when an agent saves something, rename and describe an
  item, make an old version current, delete an item (it stays in git history), show it in
  Finder, drop files or chat exports on the page to add them, archive status.
- Claude Desktop: `artikeep install --agents claude-desktop` wires the MCP server into
  `claude_desktop_config.json`, so a chat can save what it made when asked.
- React components (`.jsx`/`.tsx`, as claude.ai makes them) open as live pages, offline too.
- Desktop notification when capturing fails (macOS, or `notify-send` on Linux), at most once
  an hour per kind of failure; `"notify": false` turns it off.
- Markdown documents bring their local images along.
- `install` links the `artikeep` command into `~/.local/bin` when that folder is on `PATH`.
- `doctor` recognises the Claude Code plugin, flags the plugin and the installer hooks both
  saving every artifact, and says how to keep transcripts.
- `scripts/e2e-codex.sh`: a live end-to-end check of the Codex adapter.
- Packaged for PyPI: each GitHub release builds and publishes `artikeep` (trusted publishing).

### Changed

- The gallery is titled artikeep, like the project.
- README with a demo, screenshots and a diagram; a Russian translation (`README.ru.md`).
- FORMAT.md lists every manifest field the code writes.

### Fixed

- The CLI help no longer offers `search --all`, which never existed.

## 0.1.0 — 2026-10-09

First version: hooks for Claude Code and Codex, importers for ChatGPT and claude.ai data
exports, `artikeep add`, a static gallery with version comparison, full-text search, an MCP
server, git sync to a private remote, and a Claude Code plugin.
