#!/usr/bin/env bash
# Launch a WIDI TUI for an e06 arm from the pinned runtime in packages/widi.
#
# The widi repo's own `npm run tui` script hardcodes --agent-dir and
# --profile for its repo-local .widi dev config, and npm runs it from
# packages/widi/apps/widi, so root-relative paths passed after `--` resolve
# against the wrong directory. Arms are launched through this wrapper
# instead: it invokes the CLI directly with the hoisted tsx binary and an
# absolute agent dir.
#
# Usage: launch.sh <a0|a1|a2> [workspace-cwd]
set -euo pipefail

variant="${1:?usage: launch.sh <a0|a1|a2> [workspace-cwd]}"
workspace="${2:-$PWD}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
case "$variant" in
	a0) suffix="a0-dynamic" ;;
	a1) suffix="a1-naive" ;;
	a2) suffix="a2-static-first" ;;
	*) echo "unknown arm: $variant (expected a0|a1|a2)" >&2; exit 2 ;;
esac
agent_dir="$root/widis/.widi-e06-${suffix}"

exec "$root/packages/widi/node_modules/.bin/tsx" \
	--tsconfig "$root/packages/widi/apps/widi/tsconfig.json" \
	"$root/packages/widi/apps/widi/src/cli.ts" \
	--cwd "$workspace" \
	--agent-dir "$agent_dir" \
	--profile p4a-e06 \
	--extension "$root/experiments/e06-static-prefix/extensions/e06-fixture-tools" \
	--mode tui
