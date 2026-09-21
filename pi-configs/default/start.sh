#!/usr/bin/env bash
set -euo pipefail

config_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec pi \
  --system-prompt "$config_dir/SYSTEM.md" \
  --session-dir "$config_dir/sessions" \
  --no-extensions \
  --extension "$config_dir" \
  "$@"
