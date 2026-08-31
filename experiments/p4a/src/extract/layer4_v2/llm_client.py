#!/usr/bin/env python3
"""OpenAI-compatible client for the local vLLM server, with guided-JSON output."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
from openai import OpenAI

from common_v2 import VLLM_BASE_URL


class LlmError(RuntimeError):
    pass


class VllmJsonClient:
    """Chat client that returns schema-constrained JSON objects.

    Uses vLLM `guided_json` when the server supports it; falls back to
    prompt-level JSON with parse-and-retry otherwise.
    """

    def __init__(
        self,
        *,
        base_url: str = VLLM_BASE_URL,
        model: str | None = None,
        max_tokens: int = 16384,
        # temp 0 + json-schema grammar degenerates into whitespace loops on some
        # papers (verified: 24K tokens of blanks); 0.7 matches the model card's
        # non-thinking recommendation and breaks the loop.
        temperature: float = 0.7,
        timeout_s: float = 600.0,
    ) -> None:
        # trust_env=False: never pick up shell proxy vars for the local vLLM host.
        self._http = httpx.Client(trust_env=False, timeout=timeout_s)
        self.client = OpenAI(base_url=base_url, api_key="EMPTY", http_client=self._http)
        self.model = model or self._detect_model()
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.guided_supported: bool | None = None

    def _detect_model(self) -> str:
        models = self.client.models.list()
        ids = [m.id for m in models.data]
        if not ids:
            raise LlmError("vLLM server reports no models")
        return ids[0]

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                raise LlmError(f"no JSON object in model output: {text[:200]!r}")
            value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise LlmError("model output is not a JSON object")
        return value

    def json_call(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_retries: int = 2,
        thinking: bool = False,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (parsed_json, telemetry).

        thinking=True lets the model reason before the JSON; the reasoning tokens
        are billed into completion_tokens (~10K extra) and are not returned, so
        callers must budget max_tokens accordingly.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            use_guided = self.guided_supported is not False
            kwargs: dict[str, Any] = {
                "extra_body": {"chat_template_kwargs": {"enable_thinking": bool(thinking)}},
            }
            if use_guided:
                # NB: vLLM 0.21 silently ignores the legacy `guided_json` extra-body
                # param (verified against this server); the OpenAI-standard
                # response_format json_schema is enforced correctly.
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "result", "schema": schema},
                }
            started = time.monotonic()
            try:
                # escalate the output budget on truncation retries (papers with
                # 100+ citation contexts can legitimately need >16K output)
                base_max = max_tokens or self.max_tokens
                effective_max = min(40960, int(base_max * (1.6 ** attempt)))
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=effective_max,
                    temperature=self.temperature,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if use_guided and self.guided_supported is None and "response_format" in message:
                    self.guided_supported = False
                    last_error = exc
                    continue
                last_error = exc
                time.sleep(2.0 * (attempt + 1))
                continue
            elapsed = time.monotonic() - started
            if use_guided and self.guided_supported is None:
                self.guided_supported = True

            choice = response.choices[0]
            text = choice.message.content or ""
            usage = response.usage
            telemetry = {
                "model": self.model,
                "guided": use_guided and self.guided_supported is not False,
                "attempt": attempt,
                "seconds": round(elapsed, 2),
                "finish_reason": choice.finish_reason,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            }
            if choice.finish_reason == "length":
                last_error = LlmError("output truncated at max_tokens")
                continue
            try:
                return self._extract_json(text), telemetry
            except (LlmError, json.JSONDecodeError) as exc:
                last_error = exc
                continue
        raise LlmError(f"LLM call failed after {max_retries + 1} attempts: {last_error}")
