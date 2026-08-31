"""Runtime limits, model budget enforcement, structured events, and notifications."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


@dataclass(frozen=True)
class AgentLimits:
    crawl_concurrency: int
    llm_concurrency: int
    max_model_calls: int
    max_total_tokens: int
    crawl_timeout_seconds: int
    model_timeout_seconds: int
    run_timeout_seconds: int
    notification_max_chars: int

    @classmethod
    def from_env(cls) -> "AgentLimits":
        return cls(
            crawl_concurrency=_bounded_env_int("CRAWL_CONCURRENCY", 3, 1, 8),
            llm_concurrency=_bounded_env_int("LLM_CONCURRENCY", 4, 1, 8),
            max_model_calls=_bounded_env_int("MAX_MODEL_CALLS", 25, 1, 200),
            max_total_tokens=_bounded_env_int("MAX_TOTAL_TOKENS", 200_000, 1_000, 5_000_000),
            crawl_timeout_seconds=_bounded_env_int("CRAWL_TIMEOUT_SECONDS", 40, 10, 180),
            model_timeout_seconds=_bounded_env_int("MODEL_TIMEOUT_SECONDS", 55, 10, 180),
            run_timeout_seconds=_bounded_env_int("RUN_TIMEOUT_SECONDS", 900, 60, 7200),
            notification_max_chars=_bounded_env_int("NOTIFICATION_MAX_CHARS", 3800, 500, 4000),
        )


class ModelBudget:
    def __init__(
        self,
        *,
        max_calls: int,
        max_tokens: int,
        initial_calls: int = 0,
        initial_tokens: int = 0,
    ):
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.calls = initial_calls
        self.tokens = initial_tokens
        self.reserved_tokens = 0
        self._lock = asyncio.Lock()

    async def reserve(self, estimated_tokens: int = 0) -> None:
        async with self._lock:
            if self.calls >= self.max_calls:
                raise RuntimeError(f"模型调用预算已用尽（上限 {self.max_calls} 次）")
            estimate = max(0, estimated_tokens)
            if self.tokens + self.reserved_tokens + estimate > self.max_tokens:
                raise RuntimeError(f"Token 预算已用尽（上限 {self.max_tokens:,}）")
            self.calls += 1
            self.reserved_tokens += estimate

    async def record(self, usage: object | None, estimated_tokens: int = 0) -> None:
        total = getattr(usage, "total_tokens", 0) or 0 if usage else 0
        async with self._lock:
            self.reserved_tokens = max(0, self.reserved_tokens - max(0, estimated_tokens))
            self.tokens += total


def emit_run_event(run_dir: str | Path, event: str, **fields: object) -> None:
    """Append a single-line JSON event; the run lock guarantees one writer process."""
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    with (directory / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def build_wecom_summary(state: dict, *, max_chars: int = 3800) -> str:
    changed = state.get("changed_urls", [])
    first_time = state.get("first_time_urls", [])
    errors = state.get("crawl_errors", {})
    usage = state.get("token_usage", {})
    lines = [
        f"### 🚀 AIGC 竞品监控摘要（{datetime.now().strftime('%Y-%m-%d')}）",
        "",
        f"> 实质变化 {len(changed)} 个｜首次建档 {len(first_time)} 个｜异常 {len(errors)} 个",
    ]
    if changed:
        lines.extend(["", "**发生实质变化**"])
        lines.extend(f"- {url}" for url in changed)
    if errors:
        lines.extend(["", "**抓取异常**"])
        lines.extend(f"- {url}：{str(error)[:120]}" for url, error in errors.items())
    lines.extend(
        [
            "",
            f"模型调用：{usage.get('model_calls', 0)} 次；Token：{usage.get('total_tokens', 0):,}",
            "详细事实、引文校验和截图请在本地工作台中复核。",
        ]
    )
    content = "\n".join(lines)
    if len(content) <= max_chars:
        return content
    marker = "\n...（摘要已按企业微信长度限制截断）"
    return content[: max_chars - len(marker)] + marker


class RunTimer:
    def __init__(self):
        self.started = time.monotonic()

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started
