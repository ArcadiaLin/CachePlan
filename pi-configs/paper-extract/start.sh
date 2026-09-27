#!/usr/bin/env bash
set -euo pipefail

# 论文抽取专用配置：不启用任何内置工具，也不加载仓库 AGENTS.md、skills 和
# prompt 模板；Agent 只能通过 extensions/ 中注册的专用工具读取论文和写入图谱。
config_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PI_CODING_AGENT_DIR="$config_dir/agent"
exec pi \
  --system-prompt "$config_dir/SYSTEM.md" \
  --append-system-prompt "$config_dir/GUIDE_ZH.md" \
  --session-dir "$config_dir/sessions" \
  --no-builtin-tools \
  --no-context-files \
  --no-skills \
  --no-prompt-templates \
  --no-extensions \
  --extension "$config_dir" \
  "$@"
