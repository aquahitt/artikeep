# artikeep

A local, versioned archive of what AI agents make for you.

Agents publish pages, canvases and documents to places you don't control: a hosted
artifact link, a chat you can lose access to, a temp folder that gets cleaned. artikeep
keeps a copy of each one on your disk the moment it is made. Every change becomes a
version, a gallery lets you browse and compare versions, and an MCP server lets any
agent search what you already have.

- **Automatic where it can be.** Hooks in Claude Code and Codex capture without the
  model having to remember anything.
- **Plain files, in git.** The archive is a folder of HTML, Markdown and JSON. It opens
  without artikeep, and syncs between machines through a private git remote.
- **No dependencies.** Python 3.9+ standard library. Nothing to `pip install` for capture.

## What gets captured

| Source | How | What |
|---|---|---|
| Claude Code | hooks, automatic | pages published with the `Artifact` tool (with all their files), Claude Design canvases, Claude Docs documents (exported tab by tab), unpublished pages in the session scratchpad |
| Codex | hooks, automatic | documents a session writes that git does not keep — reports, pages, tables in temp folders, untracked or ignored files — plus the session's visualizations |
| ChatGPT | `artikeep import chatgpt <export.zip>` | canvas documents, with every edit replayed as a version |
| claude.ai | `artikeep import claude-ai <export.zip>` | artifacts from chats, with every update as a version; React components open as live pages, offline too |
| Anything else | `artikeep add <file or folder>`, or the MCP `save_artifact` tool | whatever you point it at |

Files git already tracks are skipped: they are safe where they are.

## Install

```bash
git clone https://github.com/aquahitt/artikeep ~/artikeep-src
python3 ~/artikeep-src/bin/artikeep init ~/artikeep        # the archive folder (a git repo)
python3 ~/artikeep-src/bin/artikeep install                # hooks + MCP for the agents found
python3 ~/artikeep-src/bin/artikeep doctor                 # check
```

`install` finds Claude Code (`~/.claude`) and Codex (`~/.codex`), adds its hooks next to
yours (nothing else is touched; every edited file is backed up first), registers the MCP
server with each agent's own `mcp add`, and puts a short rules block into
`~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`. `--agents codex` limits it, `--dry-run`
shows the changes, `--uninstall` removes them.

To sync across machines, give the archive a **private** remote:
`artikeep init ~/artikeep --remote git@github.com:you/my-artifacts.git`. The background
pass commits after each capture and pushes.

**Claude Code plugin.** Instead of `install`, Claude Code users can add the plugin:
`/plugin marketplace add aquahitt/artikeep`, then `/plugin install artikeep@artikeep`.
It brings the same hooks and MCP server; Codex still needs `artikeep install --agents codex`.
Use one or the other for Claude Code, not both (`artikeep doctor` flags it). The plugin
keeps copies in `~/artikeep` from the first artifact on; run `artikeep init` (with
`--remote` if you want sync) to give that folder git history, and set
`"cleanupPeriodDays": 3650` in `~/.claude/settings.json` yourself — a plugin cannot change
it, and `doctor` reminds you.

Claude Code deletes session transcripts after 30 days by default. `install` raises
`cleanupPeriodDays` to ten years: transcripts are the last place a lost artifact can be
recovered from.

## Use

```bash
artikeep open                      # the gallery: filters by project, source, type; versions; compare
artikeep search kitchen layout     # full-text, any language
artikeep add ~/Downloads/report.pdf --title "Q3 report"
artikeep import chatgpt ~/Downloads/chatgpt-export.zip
artikeep scan codex --all          # archive deliverables from past Codex sessions
```

(`artikeep` here is `python3 <clone>/bin/artikeep`, or the command from `pip install .`)

**From any agent**, through MCP:

| Tool | Does |
|---|---|
| `search_artifacts` | find items by words, source, type |
| `read_artifact` | metadata, file list and text of an item or one of its versions |
| `list_versions` | versions with time, label and size of change |
| `diff_versions` | changed text lines between two versions |
| `save_artifact` | keep a page or document (off unless `--mcp-save`) |

By default an agent sees only items made in the repository it works in. See
[SECURITY.md](SECURITY.md) for why, and how to widen it.

## The gallery

`index.html` at the archive root: a static page that works from disk. Grid or list,
filters (project, source, type, how the copy was made), groups, full-text search,
a panel per item with its version history, side-by-side comparison of any two versions
with the changed text lines. Light and dark, English and Russian, usable on a phone.

## How it works

Hooks only copy files and start a detached background pass, so an agent never waits on
disk or network. The background pass renders viewers (Design canvases, Markdown
documents, React components with the libraries claude.ai artifacts may import: React,
Tailwind, recharts, lucide-react, lodash, d3, mathjs, PapaParse, SheetJS, three, Tone,
Chart.js, and stand-ins for shadcn/ui), makes offline copies with CDN scripts and fonts vendored, updates the search
index (SQLite FTS5) and the gallery, then commits and pushes. The on-disk layout is
specified in [FORMAT.md](FORMAT.md); any tool can write into it.

## Limits, honestly

- **macOS and Linux.** Windows is not supported (file locking uses `fcntl`).
- **Host formats are undocumented.** The hook inputs of Claude Code's `Artifact` tool,
  Codex rollouts and the Claude Docs export can change with any release. artikeep logs
  every raw hook input to `.hooklog/payloads.jsonl`, and on session start checks recent
  transcripts for publishes it missed and archives them late. `artikeep doctor` shows
  when each source last saved something.
- **Importers are checked against documented shapes and synthetic exports**, not yet
  against many real ones. Anything they do not recognise is counted and reported, not
  guessed. Please open an issue with an anonymised sample if an import comes out wrong.
- **Codex has no artifact tool.** artikeep recognises deliverables by extension, by being
  outside git, and by being named in the final answer. A file a script wrote and the
  answer never mentioned is missed.
- **Web chats are not captured live.** ChatGPT and claude.ai come in through their data
  exports, which you request by hand.

## License

MIT.
