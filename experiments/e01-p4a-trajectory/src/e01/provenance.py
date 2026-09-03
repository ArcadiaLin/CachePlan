"""产物来源标注。

AGENTS.md 要求：派生产物入 `data/processed/`，并标注来源 tar.gz 版本、脚本、日期。
本模块把这件事做成每个阶段脚本都必须调用的一步，而不是靠人记得写。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

# 仓库根，从本文件位置反推：src/e01/provenance.py -> e01-p4a-trajectory -> experiments -> 根
REPO_ROOT = Path(__file__).resolve().parents[4]

RAW_ARCHIVE = REPO_ROOT / "data" / "raw" / "kimi-p4a-sessions.tar.gz"
RAW_ROOT = (
    REPO_ROOT / "data" / "raw" / "kimi-p4a-sessions" / ".kimi-code" / "sessions"
)
OUT_ROOT = REPO_ROOT / "data" / "processed" / "e01"

# 解包时记录的来源指纹。换数据集时必须一并更新，否则 --verify-source 会报错。
EXPECTED_ARCHIVE_MD5 = "9cfa1d2400d2fe283c0850a14804940b"
EXPECTED_ARCHIVE_BYTES = 365841989


def _git_rev() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_fingerprint(verify: bool = False) -> dict:
    """来源 tar.gz 的指纹。

    默认只记体积（便宜）。`verify=True` 时才算 md5（350MB，数秒），
    并在与 EXPECTED_ARCHIVE_MD5 不符时抛错 —— 这是防止分析悄悄换了输入数据。
    """
    fp: dict = {
        "archive": str(RAW_ARCHIVE.relative_to(REPO_ROOT)),
        "expected_md5": EXPECTED_ARCHIVE_MD5,
        "expected_bytes": EXPECTED_ARCHIVE_BYTES,
        "md5_verified": False,
    }
    if RAW_ARCHIVE.exists():
        fp["bytes"] = RAW_ARCHIVE.stat().st_size
        if fp["bytes"] != EXPECTED_ARCHIVE_BYTES:
            fp["warning"] = "体积与记录不符，来源可能已被替换"
        if verify:
            got = _md5(RAW_ARCHIVE)
            fp["md5"] = got
            fp["md5_verified"] = True
            if got != EXPECTED_ARCHIVE_MD5:
                raise SystemExit(
                    f"来源 tar.gz 的 md5 不符：期望 {EXPECTED_ARCHIVE_MD5}，实得 {got}。"
                    " 若确实换了数据集，请更新 provenance.EXPECTED_ARCHIVE_MD5。"
                )
    else:
        fp["warning"] = "tar.gz 不在本机；仅凭解包目录无法核实来源版本"
    return fp


def header(script: str, params: dict | None = None, verify_source: bool = False) -> dict:
    """每个产物文件的第一行。"""
    return {
        "_provenance": {
            "script": script,
            "experiment": "E01",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "git_rev": _git_rev(),
            "python": os.sys.version.split()[0],
            "source": source_fingerprint(verify=verify_source),
            "params": params or {},
        }
    }


def open_out(name: str, root: Path | None = None) -> Path:
    """产物路径。`root` 只在自检时用到：把局部结果写去临时目录，
    避免 `--limit` 跑出来的东西覆盖全量产物。"""
    root = root or OUT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def write_jsonl(name: str, header_obj: dict, rows, root: Path | None = None) -> Path:
    path = open_out(name, root)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header_obj, ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def write_json(name: str, header_obj: dict, payload: dict, root: Path | None = None) -> Path:
    path = open_out(name, root)
    obj = dict(header_obj)
    obj.update(payload)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def read_jsonl(path: Path):
    """读回产物，跳过 _provenance 头行。"""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "_provenance" in obj and len(obj) == 1:
                continue
            yield obj
