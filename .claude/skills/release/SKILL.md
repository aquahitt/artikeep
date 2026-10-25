---
name: release
description: Cut a new artikeep release - pick the version, write the CHANGELOG entry, bump the version files, merge through a PR, push the vX.Y.Z tag and verify that PyPI, the GitHub release and the plugin picked it up. Use when the user asks to release, publish, ship a version, or push artikeep to PyPI.
---

# Releasing artikeep

A release is a tag. Pushing `vX.Y.Z` on `main` runs `.github/workflows/publish.yml`: the
test matrix, `release.py check` (tag, version files and CHANGELOG agree), `build.sh`
(sdist + wheel, smoke-tested), upload to PyPI through trusted publishing, then the GitHub
release with the CHANGELOG entry as notes and the dist files attached. The Claude Code
plugin has no separate channel: it reads the version from `.claude-plugin/plugin.json` on
`main`.

Tools, all in `.github/ci/` (standard library, run from the repo root):

| Command | Does |
|---|---|
| `python3 .github/ci/release.py version` | the version the files carry (fails if they disagree) |
| `python3 .github/ci/release.py bump X.Y.Z` | sets it in `pyproject.toml`, `artikeep/__init__.py`, `.claude-plugin/plugin.json`; renames `## Unreleased` to `## X.Y.Z — today` |
| `python3 .github/ci/release.py check [--tag vX.Y.Z]` | what CI runs before building |
| `python3 .github/ci/release.py notes [X.Y.Z]` | the release notes CI will publish |
| `.github/ci/build.sh` | builds `dist/` and checks the installed wheel's `artikeep --version` |

Pushing a tag, merging to `main` and publishing are public and cannot be taken back (PyPI
never accepts the same version twice). Ask the user before each of them unless they said
to go all the way.

## 1. Preflight

- On `main`, clean, in sync with `origin/main`; the last CI run on `main` is green
  (`gh run list --branch main --limit 3`).
- Last release: `git describe --tags --abbrev=0`. What changed since:
  `git log --oneline <last tag>..HEAD`, and read the diffs that matter for users.

## 2. Version

Semantic versioning, pre-1.0 style: a new feature or a change in the archive format,
the CLI or the MCP tools bumps the minor (`0.2.0` to `0.3.0`); fixes and docs bump the
patch. If the user named a version, use it. Otherwise propose one with a one-line reason.
A change to the archive format must also be reflected in FORMAT.md.

## 3. CHANGELOG entry

On a branch `release/X.Y.Z`. Add `## Unreleased` at the top of `CHANGELOG.md` (or
complete it if it is already there) and write the entry from the commits:

- Sections `### Added`, `### Changed`, `### Fixed`, only those that have items.
- Written for the people who use artikeep: what they can now do or what stopped breaking,
  named by command, setting or agent. No commit hashes, refactors, CI or test-only changes.
- Same voice as the entries already there: short plain sentences, backticks for commands.

Then `python3 .github/ci/release.py bump X.Y.Z`. It dates the entry and sets the version.

## 4. Check locally

```bash
python3 .github/ci/release.py check --tag vX.Y.Z
python3 -m unittest discover -s tests -t .
.github/ci/build.sh
python3 .github/ci/release.py notes
```

Show the user the notes. If README.md or README.ru.md mention something the release
changes, update both (they are translations of each other).

## 5. Merge

Commit as `artikeep X.Y.Z` with a body that lists the highlights, push the branch, open a
PR (if `gh pr create` fails, `gh api repos/aquahitt/artikeep/pulls -f title=… -f head=…
-f base=main -f body=…`). Wait for its CI, merge, delete the branch, update local `main`.

## 6. Tag

```bash
git tag -a vX.Y.Z -m "artikeep X.Y.Z" origin/main   # the merged commit, not a local one
git push origin vX.Y.Z
```

## 7. Watch and verify

- `gh run list --workflow publish.yml --limit 1`, then `gh run watch <id> --exit-status`.
- PyPI: `curl -s https://pypi.org/pypi/artikeep/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"`
  prints X.Y.Z (the CDN can lag a minute).
- `uvx artikeep@X.Y.Z --version` prints `artikeep X.Y.Z`.
- `gh release view vX.Y.Z` shows the notes and two dist files, marked latest.

Report to the user: the version, the PyPI and release links, and what users run to
upgrade (`uv tool install --upgrade artikeep`, `claude plugin update artikeep@artikeep`).

## When it fails

- **Before the `pypi` job** (tests, check, build): nothing is public except the tag.
  Fix on a branch and merge, then move the tag:
  `git push origin :refs/tags/vX.Y.Z && git tag -d vX.Y.Z`, and tag again (step 6).
- **The `pypi` job**: trusted publishing is bound to the file name `publish.yml` and the
  environment `pypi`; if either was renamed, fix the publisher on pypi.org (only the
  owner can, in the browser). Then rerun the failed jobs: `gh run rerun <id> --failed`.
- **After the upload** (only `github-release` failed): `gh run rerun <id> --failed`, or
  run the whole workflow by hand for the tag: `gh workflow run publish.yml -f tag=vX.Y.Z`
  (a manual run skips files already on PyPI and fills in what is missing).
- **A broken release is on PyPI**: it cannot be replaced. Yank it on pypi.org if it harms
  users, and release X.Y.(Z+1) with the fix.
