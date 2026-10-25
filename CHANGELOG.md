# Changelog

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
