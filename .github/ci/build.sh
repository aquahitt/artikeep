#!/usr/bin/env bash
# Build the sdist and wheel into dist/, then install the wheel into a throwaway venv and
# check that the installed command reports the version the files carry.
# Needs the `build` package (pip install build) or uv.
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=${PYTHON:-python3}
version=$("$PY" .github/ci/release.py version)
rm -rf dist build ./*.egg-info

if "$PY" -c "import build" 2>/dev/null; then
  "$PY" -m build
elif command -v uv >/dev/null; then
  uv build
else
  echo "build.sh: needs 'pip install build' or uv" >&2
  exit 1
fi

wheel=$(ls dist/artikeep-"$version"-*.whl)
ls dist/artikeep-"$version".tar.gz >/dev/null

venv=$(mktemp -d)
trap 'rm -rf "$venv"' EXIT
"$PY" -m venv "$venv"
"$venv/bin/python" -m pip install -q --disable-pip-version-check "$wheel"
got=$("$venv/bin/artikeep" --version)
if [ "$got" != "artikeep $version" ]; then
  echo "build.sh: the wheel says '$got', expected 'artikeep $version'" >&2
  exit 1
fi
"$venv/bin/python" -m artikeep --help >/dev/null
echo "built and checked: $(ls dist | tr '\n' ' ')"
