# Security and privacy

The archive holds everything you made with agents: plans, reports, internal pages,
sometimes data pasted into a conversation. Treat it like your mail.

**Keep the remote private.** artikeep pushes wherever the archive's git `origin`
points. It never creates a remote and never makes anything public. Hosting the archive
as a public site (GitHub Pages and the like) publishes all of it.

**Attaching to a pull request.** `artikeep attach` commits two screenshots of an archived
page to a branch of the PR's repository (`artikeep-attachments`), because GitHub cannot take
images through its API, and posts a comment with them and the changed text lines. Everyone who
can read that repository can then see them. A public repository is refused unless you pass
`--public`; the request behind a version is quoted only with `--with-request`; `--dry-run`
prints the comment and changes nothing.

**Secrets in artifacts.** Agents sometimes put a real key or token into a page or a log. Before
each push, artikeep checks the lines the unpushed commits add for well-known secret shapes
(cloud and GitHub keys, Slack, Stripe, Anthropic/OpenAI and Telegram tokens, private keys, and
`key = "..."` values that look random). On a hit the files stay on disk and the push is held
back, with a desktop notification and the file and line in `artikeep secrets` and `artikeep
doctor`. `artikeep allow ITEM` marks a false alarm; deleting the item makes the push squash the
unpushed commits, so the text is never sent. `"secret_scan": "warn"` pushes and tells you,
`"off"` skips the check. It is a short pattern list, not a guarantee: it catches the loud,
common leaks, not every secret, and it does not look at what is already on the remote.

**MCP scope.** An agent that reads web pages, issues or files can be steered by text
hidden in them (prompt injection). If that agent can also read your whole archive and
reach the network, the archive becomes something it can leak. So by default the MCP
server shows an agent only the items made in the repository it is working in, and
every result is labelled as archived data, not instructions. Widen it deliberately:
`artikeep install --mcp-scope all`, or `"mcp_scope": "all"` in `artikeep.json`.

**Prompts in the archive.** Each version records the user request behind it (up to 500
characters, pasted material replaced by a marker) so the history can say why it exists.
If you paste secrets into prompts, they land in `manifest.json`, and with a git remote
they are pushed with it. `"provenance": false` in `artikeep.json` stops recording them;
requests already saved stay in the manifest until you edit it. Through MCP they are labelled as archived data like everything else.

**Claude Desktop is the exception.** Its chat runs outside any repository and has no hooks,
so its server sees all projects and may save: asking Claude to save is the only way a chat
artifact gets in. If you use connectors or web search in Desktop chats and want less exposure,
remove the entry (`artikeep install --agents claude-desktop --uninstall`) and rely on data
exports instead.

**`artikeep serve` listens on 127.0.0.1 only.** Archived pages are served from a second
port, a different origin, so their JavaScript can neither read the gallery nor call its API.
Every API call needs a token that exists only in the gallery page of the current run, the
API answers no CORS preflight, and it rejects any Host header other than 127.0.0.1 or
localhost (DNS rebinding). The content port serves `items/` and `drafts/` and nothing else:
not the manifest, logs or cache.

**Writing through MCP is off** unless you enable it (`--mcp-save`). Saving cannot
overwrite history: a save adds a version, and the previous ones stay.

**Hooks never block your agent.** Every hook command is guarded to exit 0, and errors
go to `.hooklog/errors.log`. A Claude Code hook exiting 2 would block the tool call;
artikeep's never do.

**No network on the capture path.** Hooks copy local files only. The background pass
uses the network for three things: downloading CDN files a page references (to make
its offline copy), `git pull`/`push` to your remote, and, if `gh` is installed and
`issue_links` is on, searching your project's GitHub issues for links to items.
Turn the last two off with `"git_push": false` and `"issue_links": false`.

**What is logged.** `.hooklog/payloads.jsonl` keeps the raw input of each hook
(file contents trimmed to 500 characters) to diagnose format changes of the host
tools. It is git-ignored and never leaves your machine. Delete it any time.

**Reporting a vulnerability.** Open a GitHub security advisory on the repository
rather than a public issue.
