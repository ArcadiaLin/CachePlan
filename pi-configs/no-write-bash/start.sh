#!/usr/bin/env bash
set -euo pipefail

config_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PI_CODING_AGENT_DIR="$config_dir/agent"
exec pi \
  --system-prompt "$config_dir/SYSTEM.md" \
  --session-dir "$config_dir/sessions" \
  --exclude-tools write,bash \
  --no-extensions \
  --extension "$config_dir" \
  "$@"
