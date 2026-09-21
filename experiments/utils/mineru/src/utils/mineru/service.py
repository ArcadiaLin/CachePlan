"""服务地址解析：调用方参数 > 环境变量 > .env 文件。

.env 不进版本管理（见仓库 .gitignore），所以这里不硬编码任何地址；
找不到就抛 RuntimeError，而不是悄悄回落到 localhost 跑出一堆连接失败。
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_KEY = "mineru_service"
PKG_ROOT = Path(__file__).resolve().parents[3]  # experiments/utils/mineru


def parse_env_file(path: Path) -> dict[str, str]:
    """极简 KEY=VALUE 解析：跳过空行与 # 注释，剥掉可选引号。"""
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        out[key.strip()] = value.strip().strip("\"'")
    return out


def env_file_candidates(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    return [Path.cwd() / ".env", PKG_ROOT / ".env"]


def resolve_server_url(explicit: str | None = None, env_file: Path | None = None) -> tuple[str, str]:
    """返回 (服务地址, 来源说明)。来源说明进日志，便于事后确认跑的是哪个服务。"""
    if explicit:
        return explicit.rstrip("/"), "server_url 参数"

    for key in (ENV_KEY.upper(), ENV_KEY):
        if os.environ.get(key):
            return os.environ[key].rstrip("/"), f"环境变量 {key}"

    for path in env_file_candidates(env_file):
        if not path.is_file():
            continue
        values = {k.lower(): v for k, v in parse_env_file(path).items()}
        if values.get(ENV_KEY):
            return values[ENV_KEY].rstrip("/"), str(path)

    tried = ", ".join(str(p) for p in env_file_candidates(env_file))
    raise RuntimeError(
        f"找不到 MinerU 服务地址：server_url= 未给，环境变量 {ENV_KEY} 未设，"
        f"下列 .env 里也没有 {ENV_KEY}= —— {tried}"
    )
