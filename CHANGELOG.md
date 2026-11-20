# Changelog

## 0.5.1 — 2026-11-20

### Fixed

- When the Claude account changes in the middle of a session (clauth, a re-login), the agent
  cannot update the artifact the other account made and publishes the same work again under a
  new link. That no longer makes a second copy: the item continues under the new link when the
  same session published the same file (or, for a Design canvas, the same type and title), and
  publishing to the earlier link finds it again. The versions are labelled "continued on a new
  link". `"continue_republished": false` turns it off. Copies made before this stay as they are.

## 0.5.0 — 2026-11-20

### Changed

- The README leads with what you gain instead of what you might lose: one place for everything
  agents make, agents that reuse their own work, every version with its reason. It adds a
  by-hand versus artikeep comparison and real numbers from a long-running archive. The package
  description follows.

### Added

- `artikeep digest [--days N] [--project P] [--format html|md] [-o FILE]` shows what the agents
  made over the last week, grouped by project: new items and items with new versions, with a
  thumbnail, the version count and the requests behind them. `html` (default) is written to
  `digest.html` in the archive and opens like the gallery; `md` is printed, to paste into a
  report or a chat.
- Collections: named groups of related items (a page, its device screenshots, the icon set).
  `artikeep collection list|show|add|remove|rename|delete`, `artikeep add FILES --collection NAME`
  and `artikeep search --collection NAME` on the command line; in `artikeep serve`, an
  "Add to a collection…" button in the item panel and a Collections filter in the gallery. An
  item can be in several; the MCP `search_artifacts` tool takes `collection`, and `read_artifact`
  names the other items kept with the one you read. The groups live in `collections.json`
  at the archive root.
- Design review in the gallery. The compare view has a **Slider** (drag across two versions
  of a page) and a **Difference** mode (black where nothing changed) next to side by side. The
  item panel shows a **filmstrip** with a thumbnail of every version (made a few per background
  pass, newest first). In `artikeep serve` a version can be marked **chosen** or **rejected**
  and an item **starred**; marks show on the version, on the card, and two filters find
  starred items and items with a chosen version.
- `artikeep attach ITEM --pr N [--from vA --to vB]` posts a before/after of an archived page as
  a pull request comment: two screenshots side by side, the text lines that changed and a link
  to the original. Running it again updates the same comment. The screenshots are committed to
  an `artikeep-attachments` branch of the repository, so a public repository needs `--public`;
  `--no-images` posts the text only and `--dry-run` shows the comment without posting.

## 0.4.0 — 2026-11-20

### Added

- Before each push the archive is checked for secrets: cloud and GitHub keys, Slack, Stripe,
  Anthropic/OpenAI and Telegram tokens, private keys and random-looking `key = "..."` values
  in what the unpushed commits add. On a hit the files stay on disk, the push is held back, you
  get a notification, and `artikeep secrets` (also `doctor`) shows the file and line.
  `artikeep allow ITEM` marks a false alarm; deleting the item lets the push go ahead without
  the text. `"secret_scan": "warn"` or `"off"` relaxes it.
- `artikeep export <id> [--version N] [--format html|zip|pdf] [-o FILE]`, and an Export button
  in `artikeep serve`, turn an archived page or canvas into one file to send. `html` inlines
  scripts, styles, images and fonts (a Design canvas carries its boards) and opens from disk
  with no network; it lists what it could not inline. `zip` is the item's files with a README.
  `pdf` prints the page with Playwright. The archive is not changed.

## 0.3.0 — 2026-11-20

### Added

- opencode is captured too. `artikeep install --agents opencode` (found automatically) adds a
  small plugin to `~/.config/opencode/plugins/` and registers the MCP server in `opencode.json`.
  When a session goes idle, the files it wrote that git does not keep are archived, with the
  request behind each one, by the same rules as Codex. `artikeep scan opencode` recovers past
  sessions from opencode's session database.
- `artikeep add` and `artikeep import` put what they keep into the project you run them in:
  the repository of the file if it is in one, else the one of the current folder. `--project PATH`
  names another, `--no-project` keeps none. Agents working in that repository now find these
  items through MCP, and the gallery's project filter groups them. An item's project can also
  be changed from its Rename dialog in `artikeep serve`.
- Each version keeps the request that led to it (the user's message, up to 500 characters)
  and the session id, for Claude Code publishes and Docs exports and for Codex deliverables.
  The gallery shows it under the version and in the compare view, search finds a version by
  the words of its request, and the MCP `list_versions` tool returns it. `"provenance": false`
  in `artikeep.json` turns it off. Versions saved earlier have none.
- `artikeep restore <id> [--version N] [--to DIR]` and the MCP `restore_artifact` tool copy an
  archived page or canvas out and say how to publish it again, for a dead link, another account,
  or to continue old work. When the agent publishes those files, the new link joins the same
  item as a new version ("republished from vN") instead of creating a duplicate.

### Fixed

- The plugin's MCP server is declared in `plugin.json`, not in a `.mcp.json` at the repository
  root. Opening a clone of the repository in Claude Code no longer starts a broken project
  server that shadowed a working `artikeep` server of the same name.

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
