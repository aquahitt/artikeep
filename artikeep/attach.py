"""`artikeep attach ITEM --pr N`: a before/after of an archived page as a pull request comment.

The comment shows two versions side by side (screenshots), the text lines that changed
and a link to the original. It carries a hidden marker, so running the command again for
the same item and versions updates that comment instead of adding another.

GitHub has no way to attach an image to a comment through its API, so the screenshots are
committed to a branch of the PR's repository, `artikeep-attachments`, and linked from there.
That publishes them to everyone who can read that repository. For this reason a public
repository is refused unless you pass --public, and the request behind a version is only
included with --with-request. --no-images posts the text part only; --dry-run prints the
comment and touches nothing.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from artikeep import export
from artikeep.gallery import text_diff
from artikeep.search import version_text
from artikeep.store import Store

BRANCH = "artikeep-attachments"
MAX_DIFF_LINES = 40
SHOT_SCRIPT = r'''
import asyncio, json, sys
from playwright.async_api import async_playwright
jobs = json.loads(sys.argv[1])
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for page, out in jobs:
            pg = await b.new_page(viewport={"width": 1100, "height": 760})
            await pg.goto("file://" + page, wait_until="load", timeout=60000)
            await pg.wait_for_timeout(1200)
            await pg.screenshot(path=out, type="jpeg", quality=82, full_page=True)
            await pg.close()
        await b.close()
asyncio.run(main())
'''


class AttachError(Exception):
    pass


def _gh(*args, input: str | None = None) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, input=input, timeout=120)
    if r.returncode != 0:
        raise AttachError("gh %s: %s" % (" ".join(args[:2]), (r.stderr.strip() or r.stdout.strip() or "failed").splitlines()[-1]))
    return r.stdout


def repo_of(store: Store, entry: dict, explicit: str | None) -> str:
    """owner/name from --repo, else from the origin remote of the item's project."""
    if explicit:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", explicit):
            raise AttachError("--repo must look like owner/name")
        return explicit
    project = entry.get("project")
    if project:
        r = subprocess.run(["git", "-C", project, "remote", "get-url", "origin"], capture_output=True, text=True)
        m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
        if m:
            return m.group(1)
    raise AttachError("cannot tell which GitHub repository this is: pass --repo owner/name")


def pick_versions(entry: dict, a, b) -> tuple:
    vs = entry.get("versions") or []
    if len(vs) < 2 and not (a and b):
        raise AttachError("%s has %d version(s): nothing to compare" % (entry["dir"], len(vs)))
    to = b or vs[-1]["n"]
    frm = a or max(1, to - 1)
    have = {v["n"] for v in vs}
    for n in (frm, to):
        if n not in have:
            raise AttachError("versions are numbered 1..%d" % len(vs))
    if frm == to:
        raise AttachError("--from and --to are the same version")
    return frm, to


def screenshots(store: Store, entry: dict, versions: list, dest: Path) -> dict:
    """{version: image path}; empty without Playwright or when the item is not a page."""
    if subprocess.run(["python3", "-c", "import playwright"], capture_output=True).returncode != 0:
        return {}
    jobs, out = [], {}
    for n in versions:
        try:
            data, _ = export.export_html(store, entry, n)
        except export.ExportError:
            return {}
        page = dest / ("v%d.html" % n)
        page.write_bytes(data)
        img = dest / ("v%d.jpg" % n)
        jobs.append([str(page), str(img)])
        out[n] = img
    r = subprocess.run(["python3", "-c", SHOT_SCRIPT, json.dumps(jobs)], capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not all(p.exists() for p in out.values()):
        raise AttachError("rendering failed: %s" % ((r.stderr.strip().splitlines() or ["unknown error"])[-1]))
    return out


def upload(repo: str, item: str, img: Path) -> str:
    """Commit the image to the attachments branch and return a URL a comment can show."""
    data = img.read_bytes()
    path = "artikeep/%s/%s-%s.jpg" % (item, img.stem, hashlib.sha256(data).hexdigest()[:10])
    try:
        _gh("api", "repos/%s/git/ref/heads/%s" % (repo, BRANCH), "--jq", ".object.sha")
    except AttachError:
        default = _gh("api", "repos/%s" % repo, "--jq", ".default_branch").strip()
        sha = _gh("api", "repos/%s/git/ref/heads/%s" % (repo, default), "--jq", ".object.sha").strip()
        _gh("api", "repos/%s/git/refs" % repo, "-f", "ref=refs/heads/%s" % BRANCH, "-f", "sha=%s" % sha)
    try:
        _gh("api", "repos/%s/contents/%s?ref=%s" % (repo, path, BRANCH), "--jq", ".sha")  # same bytes already there
    except AttachError:
        _gh("api", "-X", "PUT", "repos/%s/contents/%s" % (repo, path), "-f", "message=artikeep: %s" % path,
            "-f", "branch=%s" % BRANCH, "-f", "content=%s" % base64.b64encode(data).decode())
    return "https://github.com/%s/blob/%s/%s?raw=true" % (repo, BRANCH, path)


def marker(item: str, frm: int, to: int) -> str:
    return "<!-- artikeep:attach:%s:%d-%d -->" % (item, frm, to)


def build_comment(store: Store, entry: dict, frm: int, to: int, urls: dict, with_request: bool = False) -> str:
    item = store.item_dir(entry)
    vs = {v["n"]: v for v in entry["versions"]}
    src = lambda n: item / vs[n]["dir"]
    diff = text_diff(version_text(src(frm)), version_text(src(to)), limit=MAX_DIFF_LINES)
    title = (entry.get("title") or entry["dir"]).replace("|", "\\|")
    lines = [marker(entry["dir"], frm, to), "### %s: v%d → v%d" % (title, frm, to), ""]
    head = lambda n: "%s (v%d, %s)" % ("Before" if n == frm else "After", n, vs[n]["at"][:16].replace("T", " "))
    if urls:
        lines += ["| %s | %s |" % (head(frm), head(to)), "|---|---|",
                  "| ![v%d](%s) | ![v%d](%s) |" % (frm, urls[frm], to, urls[to]), ""]
    else:
        lines += ["%s → %s" % (head(frm), head(to)), ""]
    if with_request and vs[to].get("request"):
        lines += ["> %s" % vs[to]["request"].replace("\n", " "), ""]
    if diff["lines"]:
        body = "\n".join("%s %s" % (c["op"], c["text"].replace("\n", " ")) for c in diff["lines"])
        more = "\n… and %d more line(s)" % diff["more"] if diff["more"] else ""
        lines += ["<details><summary>Changed text: +%d −%d</summary>" % (diff["add"], diff["rem"]), "", "```diff", body + more, "```", "</details>", ""]
    else:
        lines += ["_The text did not change; the difference is in how it looks._", ""]
    if entry.get("url"):
        lines += ["Original: %s" % entry["url"], ""]
    lines.append("<sub>Kept by [artikeep](https://github.com/aquahitt/artikeep).</sub>")
    return "\n".join(lines)


def post(repo: str, pr: int, body: str, mark: str) -> tuple:
    """(url, updated?) Creates the comment, or updates ours that carries the same marker."""
    me = _gh("api", "user", "--jq", ".login").strip()
    found = _gh("api", "--paginate", "repos/%s/issues/%d/comments" % (repo, pr),
                "--jq", '.[] | select(.user.login == "%s" and (.body | contains("%s"))) | .id' % (me, mark)).split()
    if found:
        out = _gh("api", "-X", "PATCH", "repos/%s/issues/comments/%s" % (repo, found[0]), "-F", "body=@-", "--jq", ".html_url", input=body)
        return out.strip(), True
    out = _gh("api", "repos/%s/issues/%d/comments" % (repo, pr), "-F", "body=@-", "--jq", ".html_url", input=body)
    return out.strip(), False


def run(store: Store, folder: str, pr: int, *, repo=None, frm=None, to=None, images=True, public=False,
        with_request=False, dry_run=False) -> dict:
    try:
        _, entry = store.find(store.load(), folder)
    except KeyError:
        raise AttachError("no item %s" % folder)
    repo = repo_of(store, entry, repo)
    frm, to = pick_versions(entry, frm, to)
    if not dry_run:
        private = _gh("api", "repos/%s" % repo, "--jq", ".private").strip() == "true"
        if not private and not public:
            raise AttachError("%s is a public repository: this would publish the archived page there. "
                              "Pass --public if that is what you want." % repo)
    urls, note = {}, None
    with tempfile.TemporaryDirectory(prefix="artikeep-attach-") as tmp:
        shots = screenshots(store, entry, [frm, to], Path(tmp)) if images else {}
        if images and not shots:
            note = "no screenshots (Playwright is not importable by python3, or the item is not a page): text only"
        if shots:
            urls = {n: ("https://github.com/%s/blob/%s/artikeep/%s/v%d-<hash>.jpg?raw=true" % (repo, BRANCH, entry["dir"], n)) if dry_run
                    else upload(repo, entry["dir"], p)
                    for n, p in shots.items()}
        body = build_comment(store, entry, frm, to, urls, with_request)
    if dry_run:
        return {"repo": repo, "pr": pr, "body": body, "note": note}
    url, updated = post(repo, pr, body, marker(entry["dir"], frm, to))
    return {"repo": repo, "pr": pr, "url": url, "updated": updated, "note": note}
