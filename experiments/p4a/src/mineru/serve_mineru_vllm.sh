#!/usr/bin/env bash
# Run from repo root:
#   src/mineru/serve_mineru_vllm.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

GPU_IDS="${GPU_IDS:-0}"
MODEL_PATH="${MODEL_PATH:-/srv/models/MinerU/MinerU2.5-Pro-2605-1.2B}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-mineru}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8004}"
ENABLE_MODELS_PROXY="${ENABLE_MODELS_PROXY:-0}"
VLLM_INTERNAL_HOST="${VLLM_INTERNAL_HOST:-127.0.0.1}"
VLLM_INTERNAL_PORT="${VLLM_INTERNAL_PORT:-8005}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.5}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"
TRUST_REMOTE_CODE="${TRUST_REMOTE_CODE:-1}"

if [[ -z "${TENSOR_PARALLEL_SIZE:-}" ]]; then
  IFS=',' read -ra _GPU_LIST <<< "${GPU_IDS}"
  TENSOR_PARALLEL_SIZE="${#_GPU_LIST[@]}"
fi

if [[ -x "${PROJECT_ROOT}/.venv/bin/vllm" ]]; then
  VLLM_BIN="${PROJECT_ROOT}/.venv/bin/vllm"
else
  VLLM_BIN="${VLLM_BIN:-vllm}"
fi

if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

export CUDA_VISIBLE_DEVICES="${GPU_IDS}"

if [[ ! -e /dev/nvidiactl ]] || ! compgen -G "/dev/nvidia[0-9]*" >/dev/null; then
  cat >&2 <<'EOF'
NVIDIA devices are not visible in this container.

Expected /dev/nvidiactl and at least one /dev/nvidia[0-9]* device. In an LXC
container, expose the NVIDIA device nodes and driver libraries from the host
before starting vLLM.
EOF
  exit 1
fi

if [[ "${ENABLE_MODELS_PROXY}" == "1" || "${ENABLE_MODELS_PROXY}" == "true" ]]; then
  VLLM_HOST="${VLLM_INTERNAL_HOST}"
  VLLM_PORT="${VLLM_INTERNAL_PORT}"
else
  VLLM_HOST="${HOST}"
  VLLM_PORT="${PORT}"
fi

cmd=(
  "${VLLM_BIN}" serve "${MODEL_PATH}"
  --host "${VLLM_HOST}"
  --port "${VLLM_PORT}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
  --logits-processors "mineru_vl_utils:MinerULogitsProcessor"
)

if [[ "${TRUST_REMOTE_CODE}" == "1" || "${TRUST_REMOTE_CODE}" == "true" ]]; then
  cmd+=(--trust-remote-code)
fi

if [[ -n "${MAX_MODEL_LEN}" ]]; then
  cmd+=(--max-model-len "${MAX_MODEL_LEN}")
fi

printf 'CUDA_VISIBLE_DEVICES=%s\n' "${CUDA_VISIBLE_DEVICES}"
printf 'Starting MinerU vLLM server on http://%s:%s\n' "${VLLM_HOST}" "${VLLM_PORT}"
printf 'Served model name: %s\n' "${SERVED_MODEL_NAME}"
printf 'After startup, verify with:\n'
printf '  curl -fsS http://%s:%s/v1/models\n' "${HOST}" "${PORT}"
printf 'Command:'
printf ' %q' "${cmd[@]}"
printf '\n'

if [[ "${ENABLE_MODELS_PROXY}" == "1" || "${ENABLE_MODELS_PROXY}" == "true" ]]; then
  "${cmd[@]}" &
  vllm_pid=$!
  cleanup() {
    kill "${vllm_pid}" 2>/dev/null || true
    wait "${vllm_pid}" 2>/dev/null || true
  }
  trap cleanup EXIT INT TERM

  "${PYTHON_BIN}" "${SCRIPT_DIR}/mineru_vllm_proxy.py" \
    --listen-host "${HOST}" \
    --listen-port "${PORT}" \
    --upstream "http://${VLLM_INTERNAL_HOST}:${VLLM_INTERNAL_PORT}" \
    --served-model-name "${SERVED_MODEL_NAME}" \
    --model-root "${MODEL_PATH}"
  proxy_status=$?
  cleanup
  exit "${proxy_status}"
else
  exec "${cmd[@]}"
fi
