#!/usr/bin/env bash
# Run A0, A1, then resume A2 over the same four cases. Each launch and every
# case within its plan runs serially; a failed arm stops the batch.
#
#   run_serial_cases.sh [--dry-run] <a2-shared-run-root> <new-comparison-run-root> [case-id ...]
#
# Omit case ids to run eval-low-01 through eval-low-04. The A2 root must have
# completed a bootstrap and be rewound to its recorded bootstrap leaf.
set -euo pipefail

dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
	dry_run=true
	shift
fi
if [[ $# -lt 2 ]]; then
	echo "usage: $0 [--dry-run] <a2-shared-run-root> <new-comparison-run-root> [case-id ...]" >&2
	exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
a2_root="$(realpath "$1")"
comparison_root="$2"
shift 2

if [[ $# -eq 0 ]]; then
	case_ids=(eval-low-01 eval-low-02 eval-low-03 eval-low-04)
else
	case_ids=("$@")
fi

if [[ ${#case_ids[@]} -ne 4 ]]; then
	echo "exactly four case ids are required" >&2
	exit 2
fi
if [[ ! -f "$a2_root/print.jsonl" || ! -f "$a2_root/run-manifest.jsonl" ]]; then
	echo "A2 root is missing print.jsonl or run-manifest.jsonl: $a2_root" >&2
	exit 2
fi
if [[ -e "$comparison_root" ]]; then
	echo "comparison run root already exists: $comparison_root" >&2
	exit 2
fi

mkdir -p "$comparison_root"
comparison_root="$(realpath "$comparison_root")"
fixture_root="$repo_root/data/processed/e06/fixtures"
skill_path="$repo_root/experiments/e06-static-prefix/skills/paper-mineru-resource-extract/SKILL.md"
batch_id="$(basename "$comparison_root")"

for case_id in "${case_ids[@]}"; do
	if [[ ! "$case_id" =~ ^[a-z]+(-[a-z]+)*-[0-9]+$ ]]; then
		echo "invalid E06 case id: $case_id" >&2
		exit 2
	fi
	if [[ ! -d "$fixture_root/$case_id/input" ]]; then
		echo "fixture does not exist: $fixture_root/$case_id" >&2
		exit 2
	fi
	if [[ -e "$a2_root/cases/$case_id" ]]; then
		echo "A2 root already contains case output: $case_id" >&2
		exit 2
	fi
done

session_ref="$(jq -ers '[.[] | select(.type == "ready") | .sessionRef][-1] // empty' "$a2_root/print.jsonl")"
bootstrap_leaf_id="$(jq -ers '[.[] | select(.type == "bootstrap_completed") | .leaf_id][0] // empty' "$a2_root/run-manifest.jsonl")"
if [[ -z "$session_ref" || -z "$bootstrap_leaf_id" ]]; then
	echo "cannot recover A2 session reference and bootstrap leaf from $a2_root" >&2
	exit 2
fi

case_json="$(jq -cn '$ARGS.positional' --args "${case_ids[@]}")"

write_fresh_plan() {
	local arm="$1"
	local run_root="$2"
	local plan_path="$3"
	jq -n \
		--arg run_id "$batch_id-$arm" \
		--arg arm "$arm" \
		--arg fixture_root "$fixture_root" \
		--arg run_root "$run_root" \
		--arg skill_path "$skill_path" \
		--argjson case_ids "$case_json" \
		'{
			schema_version: 1,
			run_id: $run_id,
			arm: $arm,
			fixture_root: $fixture_root,
			run_root: $run_root,
			skill_path: $skill_path,
			case_ids: $case_ids
		}' > "$plan_path"
}

write_a2_resume_plan() {
	local plan_path="$1"
	jq -n \
		--arg run_id "$batch_id-a2" \
		--arg fixture_root "$fixture_root" \
		--arg run_root "$a2_root" \
		--arg skill_path "$skill_path" \
		--arg session_ref "$session_ref" \
		--arg bootstrap_leaf_id "$bootstrap_leaf_id" \
		--argjson case_ids "$case_json" \
		'{
			schema_version: 1,
			run_id: $run_id,
			arm: "a2",
			fixture_root: $fixture_root,
			run_root: $run_root,
			skill_path: $skill_path,
			case_ids: $case_ids,
			resume_session_ref: $session_ref,
			bootstrap_leaf_id: $bootstrap_leaf_id
		}' > "$plan_path"
}

for arm in a0 a1; do
	run_root="$comparison_root/$arm"
	mkdir -p "$run_root"
	plan_path="$run_root/run-plan.json"
	write_fresh_plan "$arm" "$run_root" "$plan_path"
	if [[ "$dry_run" == false ]]; then
		echo "[e06] starting $arm: ${case_ids[*]}"
		bash "$script_dir/launch.sh" "$arm" "$plan_path"
	fi
done

a2_plan="$a2_root/$batch_id-a2-resume-plan.json"
write_a2_resume_plan "$a2_plan"
if [[ "$dry_run" == true ]]; then
	echo "[e06] wrote serial batch plans without launching: $batch_id"
	exit 0
fi

echo "[e06] resuming A2 root $session_ref: ${case_ids[*]}"
bash "$script_dir/launch.sh" a2 "$a2_plan"

echo "[e06] completed serial batch $batch_id"
