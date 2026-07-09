#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
INSTALL_SPEC="${KEDI_INSTALL_SPEC:-${REPO_ROOT}}"

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi

  curl -LsSf https://astral.sh/uv/install.sh | sh

  export PATH="${HOME}/.cargo/bin:${HOME}/.local/bin:${PATH}"
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv installation completed, but uv is not on PATH." >&2
    echo "Add ~/.cargo/bin or ~/.local/bin to PATH and rerun this script." >&2
    exit 1
  fi
}

ensure_binary() {
  local name="$1"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo "Expected ${name} to be available on PATH after installation." >&2
    exit 1
  fi
}

ensure_uv

uv tool install --force "${INSTALL_SPEC}"
uv tool install --force "${SCRIPT_DIR}" --with "${INSTALL_SPEC}"

export PATH="${HOME}/.cargo/bin:${HOME}/.local/bin:${PATH}"

ensure_binary kedi
ensure_binary kedi-mcp

kedi --help >/dev/null
kedi-mcp --help >/dev/null

echo "Installed kedi and kedi-mcp successfully."
