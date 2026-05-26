#!/usr/bin/env bash
# Install or update the Arena backend's Python dependencies on Replit.
#
# Replit's Nix environment refuses plain `pip install` per PEP 668. We use
# `uv pip install --target=<site-packages>` so packages land in the
# project-persistent .pythonlibs/ directory that is already on sys.path.
#
# Usage:
#   scripts/install_python_deps.sh            # install everything in requirements.txt
#   scripts/install_python_deps.sh deap numpy # install or upgrade specific packages
#
# Re-running is safe; uv is a no-op when versions are already satisfied.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${REPO_ROOT}/.pythonlibs/lib/python3.11/site-packages"
REQ_FILE="${REPO_ROOT}/artifacts/backend/requirements.txt"

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv not found on PATH. Replit usually ships it via Nix; check your .replit toolchain." >&2
    exit 1
fi

mkdir -p "${TARGET}"

if [[ $# -gt 0 ]]; then
    echo "Installing/upgrading: $*"
    uv pip install --target="${TARGET}" "$@"
else
    if [[ ! -f "${REQ_FILE}" ]]; then
        echo "error: ${REQ_FILE} not found" >&2
        exit 1
    fi
    echo "Installing from ${REQ_FILE} into ${TARGET}"
    uv pip install --target="${TARGET}" -r "${REQ_FILE}"
fi

echo "Done. Verify with: python3 -c 'import deap, numpy; print(deap.__version__, numpy.__version__)'"
