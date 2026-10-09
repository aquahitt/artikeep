# Security and privacy

The archive holds everything you made with agents: plans, reports, internal pages,
sometimes data pasted into a conversation. Treat it like your mail.

**Keep the remote private.** artikeep pushes wherever the archive's git `origin`
points. It never creates a remote and never makes anything public. Hosting the archive
as a public site (GitHub Pages and the like) publishes all of it.

**MCP scope.** An agent that reads web pages, issues or files can be steered by text
hidden in them (prompt injection). If that agent can also read your whole archive and
reach the network, the archive becomes something it can leak. So by default the MCP
server shows an agent only the items made in the repository it is working in, and
every result is labelled as archived data, not instructions. Widen it deliberately:
`artikeep install --mcp-scope all`, or `"mcp_scope": "all"` in `artikeep.json`.

**Claude Desktop is the exception.** Its chat runs outside any repository and has no hooks,
so its server sees all projects and may save: asking Claude to save is the only way a chat
artifact gets in. If you use connectors or web search in Desktop chats and want less exposure,
remove the entry (`artikeep install --agents claude-desktop --uninstall`) and rely on data
exports instead.

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
