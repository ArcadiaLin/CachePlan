#!/usr/bin/env bash
# Run one E06 arm through WIDI print mode, driven by the execution-prefix
# extension rather than an interactive TUI.
#
# Usage: launch.sh <a0|a1|a2> <run-plan.json>
set -euo pipefail

if [[ $# -ne 2 ]]; then
	echo "usage: launch.sh <a0|a1|a2> <run-plan.json>" >&2
	exit 2
fi

variant="$1"
plan="$(realpath "$2")"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

case "$variant" in
	a0) suffix="a0-dynamic" ;;
	a1) suffix="a1-naive" ;;
	a2) suffix="a2-static-first" ;;
	*) echo "unknown arm: $variant (expected a0|a1|a2)" >&2; exit 2 ;;
esac

plan_arm="$(jq -er '.arm' "$plan")"
run_root="$(jq -er '.run_root' "$plan")"
has_resume="$(jq -r 'has("resume_session_ref")' "$plan")"
has_bootstrap_leaf="$(jq -r 'has("bootstrap_leaf_id")' "$plan")"
if [[ "$plan_arm" != "$variant" ]]; then
	echo "run plan arm $plan_arm does not match requested arm $variant" >&2
	exit 2
fi
if [[ "$run_root" != /* ]]; then
	echo "run plan run_root must be absolute" >&2
	exit 2
fi
if [[ "$has_resume" != "$has_bootstrap_leaf" ]]; then
	echo "run plan must provide resume_session_ref and bootstrap_leaf_id together" >&2
	exit 2
fi
if [[ "$has_resume" == "true" && "$variant" != "a2" ]]; then
	echo "only A2 run plans may resume a shared root" >&2
	exit 2
fi

run_mode=(--profile p4a-e06)
if [[ "$has_resume" == "true" ]]; then
	resume_session_ref="$(jq -er '.resume_session_ref | strings | select(length > 0)' "$plan")"
	run_mode=(--resume "$resume_session_ref")
fi

mkdir -p "$run_root/active"
agent_dir="$root/widis/.widi-e06-${suffix}"
event="$(jq -cn --arg plan_path "$plan" '{name: "e06-execution-prefix:run", payload: {plan_path: $plan_path}}')"

print_log="$run_root/print.jsonl"
set +e
env \
	E06_ARM="$variant" \
	E06_STATIC_KNOWLEDGE="$root/experiments/e06-static-prefix/static-knowledge.md" \
	"$root/packages/widi/node_modules/.bin/tsx" \
	--tsconfig "$root/packages/widi/apps/widi/tsconfig.json" \
	"$root/packages/widi/apps/widi/src/cli.ts" \
	--cwd "$run_root/active" \
	--agent-dir "$agent_dir" \
	"${run_mode[@]}" \
	--extension "$root/experiments/e06-static-prefix/extensions/e06-fixture-tools" \
	--extension "$root/experiments/e06-static-prefix/extensions/e06-execution-prefix" \
	--mode print \
	--output json \
	--emit "$event" | tee "$print_log"
widi_status="${PIPESTATUS[0]}"
set -e

if jq -e 'select(.type == "extension_event" and .event.name == "e06-execution-prefix:failed")' "$print_log" >/dev/null; then
	exit 1
fi
exit "$widi_status"
