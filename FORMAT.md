# Archive format, version 1

An artikeep archive is a folder. Everything a reader needs is in plain files; the
search index and logs are caches that can be deleted at any time. Other tools may
write items into an archive as long as they follow this document.

```
<archive>/
  manifest.json          the item list (below)
  artikeep.json          settings (optional; see artikeep/config.py for keys)
  index.html             the gallery, regenerated
  items/<dir>/           one folder per item: its newest files
    versions/NNN-<time>/ a frozen copy of every distinct state, oldest first
    server/index.html    optional: the host's copy, saved when an agent read it back
    index.offline.html   optional: index.html with CDN files vendored into _vendor/
    _thumb.jpg           optional: gallery thumbnail
  drafts/<date>-<id>/    unpublished pages mirrored from agent session folders
    _meta.json           {"session", "agent", "project"}
  .gitignore             lists .hooklog/ and .cache/
  .hooklog/              not committed: errors.log, payloads.jsonl, locks
  .cache/                not committed: index.sqlite (search)
```

## manifest.json

```json
{"version": 1, "items": {"<key>": { ...entry... }}}
```

The **key** identifies an item by its origin, so the same artifact always lands in the
same entry: a URL (`https://claude.ai/artifact/…`), or a prefixed id:
`codex:<absolute path>`, `chatgpt:<conversation>:<n>`, `claude-ai:<conversation>:<artifact id>`,
`file:<absolute path>`, `mcp:<project>:<slug>:<file name>`, `local:<path>`.

Entry fields (all optional except `dir`):

| Field | Meaning |
|---|---|
| `dir` | folder name under `items/`, `YYYY-MM-DD-<slug>` of the first save, unique |
| `title`, `description` | for people |
| `agent` | `claude-code`, `codex`, `chatgpt`, `claude-ai`, `import`, `mcp`; absent means `claude-code` |
| `project` | absolute path of the git repository the item was made in |
| `url` | where the original lives on the web |
| `origin` | the source path or URL, when not a web original |
| `main` | file to open, relative to the item folder; default `index.html` |
| `created`, `updated` | ISO 8601 with offset |
| `versions` | `[{"n", "at", "label", "dir", "changed", "diff"?}]`, `dir` relative to the item folder; `changed` lists files that differ from the previous version (`-name` for removed) |
| `publishes` | one record per save: `{"at", "session", "source", "copied", ...}` |
| `kind` | `claude-doc` for Claude Docs documents |
| `deleted` | time the original was deleted at the source; the copy stays |
| `restore_fidelity` | for items recovered after the fact: `exact`, `recreated`, `missing` |
| `issues` | GitHub issue numbers that link to the item |
| `service` | true for test items the gallery hides by default |
| `sha256` | hash of the single source file (Codex), to skip unchanged saves |

## Versions

A save copies the new files into `items/<dir>/`, then compares every file (except
`versions/`, `_vendor/`, `server/`, generated viewers, the offline copy and the
thumbnail) with the newest version. If anything differs, the whole set is copied to
`versions/NNN-YYYYMMDDTHHMM/` and appended to `versions`. Identical saves add nothing.

## Generated pages

`index.html` inside an item is either the published page or a viewer artikeep generated
(a Claude Design canvas, or Markdown documents named `doc-*.md` or given as `main`).
Viewers start with the comment `<!-- artikeep canvas viewer -->` or
`<!-- artikeep doc viewer -->` and are rebuilt when their sources change; they are not
part of versions. Any HTML file written by artikeep gets `<meta charset="utf-8">` if it
lacks one.
