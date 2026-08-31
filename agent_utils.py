"""Shared safety, path, diff, persistence, and locking helpers."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent
DEMO_DATA_DIR = PROJECT_ROOT / "data"
DEMO_REPORT_DIR = PROJECT_ROOT / "reports"
_runtime_override = os.getenv("AGENT_RUNTIME_DIR", "").strip()
RUNTIME_ROOT = Path(_runtime_override or PROJECT_ROOT / "runtime").expanduser().resolve()
DATA_DIR = RUNTIME_ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
LOG_DIR = DATA_DIR / "logs"
REPORT_DIR = RUNTIME_ROOT / "reports"
COMPETITORS_CONFIG_PATH = DATA_DIR / "competitors.json"
DEMO_COMPETITORS_CONFIG_PATH = DEMO_DATA_DIR / "competitors.json"
RUN_LOCK_PATH = RUNTIME_ROOT / ".agent-run.lock"


def ensure_runtime_layout() -> None:
    for path in (SNAPSHOT_DIR, SCREENSHOT_DIR, LOG_DIR, REPORT_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not COMPETITORS_CONFIG_PATH.exists() and DEMO_COMPETITORS_CONFIG_PATH.exists():
        atomic_write_text(
            COMPETITORS_CONFIG_PATH,
            DEMO_COMPETITORS_CONFIG_PATH.read_text(encoding="utf-8-sig"),
        )


def merged_artifact_files(runtime_dir: str | Path, demo_dir: str | Path, pattern: str) -> list[str]:
    """Return runtime artifacts plus demo fallbacks, preferring runtime by filename."""
    selected: dict[str, Path] = {}
    for directory in (Path(demo_dir), Path(runtime_dir)):
        if directory.exists():
            for path in directory.glob(pattern):
                selected[path.name] = path
    return [str(path) for path in sorted(selected.values(), key=lambda item: item.name)]


def atomic_write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: str | Path, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_SPACE_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_RE = re.compile(r"\n{3,}")


def normalize_content(content: str) -> str:
    """Reduce crawler noise while preserving user-visible wording and prices."""
    text = content.replace("\ufeff", "").replace("\u200b", "")
    text = _IMAGE_RE.sub(lambda match: match.group(1), text)
    text = _LINK_RE.sub(lambda match: match.group(1), text)
    normalized_lines = []
    for raw_line in text.splitlines():
        line = _SPACE_RE.sub(" ", raw_line).strip()
        if line:
            normalized_lines.append(line)
    return _BLANK_RE.sub("\n\n", "\n".join(normalized_lines)).strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()


def site_key_for_url(url: str) -> str:
    clean = re.sub(r"^https?://", "", url).rstrip("/")
    return re.sub(r"[^\w\-.]", "_", clean)


@dataclass(frozen=True)
class ChangeAssessment:
    changed: bool
    similarity: float
    changed_characters: int
    diff_context: str


def assess_change(
    old_content: str,
    new_content: str,
    *,
    min_changed_characters: int = 24,
    min_change_ratio: float = 0.003,
    max_diff_characters: int = 8000,
) -> ChangeAssessment:
    old = normalize_content(old_content)
    new = normalize_content(new_content)
    if old == new:
        return ChangeAssessment(False, 1.0, 0, "正文规范化后完全一致。")

    matcher = SequenceMatcher(None, old, new, autojunk=False)
    similarity = matcher.ratio()
    changed_characters = round(max(len(old), len(new)) * (1 - similarity))
    relative_change = 1 - similarity
    diff_lines = unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile="previous",
        tofile="current",
        lineterm="",
        n=2,
    )
    diff_context = "\n".join(diff_lines)
    changed_fragments = []
    change_contexts = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_fragments.extend((old[old_start:old_end], new[new_start:new_end]))
        change_contexts.extend(
            (
                old[max(0, old_start - 24) : min(len(old), old_end + 24)],
                new[max(0, new_start - 24) : min(len(new), new_end + 24)],
            )
        )
    fragment_text = " ".join(changed_fragments).strip()
    context_text = " ".join(change_contexts)
    numeric_only_change = bool(fragment_text) and not re.search(r"[^\W\d_]", fragment_text)
    if numeric_only_change:
        signal_pattern = r"价格|定价|套餐|折扣|积分|额度|版本|元|¥|￥|%"
    else:
        signal_pattern = r"价格|定价|套餐|免费|折扣|积分|额度|版本|上线|发布|新增|下线|功能|API|模型"
    high_signal = bool(re.search(signal_pattern, context_text, flags=re.IGNORECASE))
    changed = (
        changed_characters >= min_changed_characters and relative_change >= min_change_ratio
    ) or (high_signal and changed_characters >= 1)
    if len(diff_context) > max_diff_characters:
        diff_context = diff_context[:max_diff_characters] + "\n...（差异内容已截断）"
    return ChangeAssessment(changed, similarity, changed_characters, diff_context)


def _is_forbidden_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value.split("%", 1)[0])
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def validate_public_http_url(url: str, *, resolve_dns: bool = False) -> str:
    """Validate a crawl target and reject local/private network destinations."""
    candidate = url.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅支持包含有效主机名的 http:// 或 https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("URL 不允许包含用户名或密码")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise ValueError("不允许访问本机或局域网主机")
    try:
        if _is_forbidden_ip(hostname):
            raise ValueError("不允许访问私网、回环、链路本地或保留地址")
    except ValueError as exc:
        if "does not appear to be" not in str(exc):
            raise

    if resolve_dns:
        try:
            default_port = 443 if parsed.scheme == "https" else 80
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or default_port)}
        except socket.gaierror as exc:
            raise ValueError(f"域名解析失败：{hostname}") from exc
        if not addresses:
            raise ValueError(f"域名未解析到地址：{hostname}")
        if any(_is_forbidden_ip(address) for address in addresses):
            raise ValueError("域名解析到了私网、回环、链路本地或保留地址")
    return candidate


def compact_error(error: object, max_length: int = 240) -> str:
    text = " ".join(str(error).replace("\r", "\n").splitlines())
    text = re.sub(r"(?:[A-Za-z]:\\|\.\.[/\\])[^\s|]+", "[local-path]", text)
    text = text.replace("|", "\\|")
    if len(text) > max_length:
        return text[: max_length - 1] + "…"
    return text or "未知异常"


def ensure_single_line(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError(f"{field_name} 不能包含换行符")
    return cleaned


class AgentRunLock(AbstractContextManager["AgentRunLock"]):
    def __init__(self, path: str | Path = RUN_LOCK_PATH, stale_after_seconds: int = 6 * 3600):
        self.path = Path(path)
        self.stale_after_seconds = stale_after_seconds
        self.acquired = False

    def __enter__(self) -> "AgentRunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"pid": os.getpid(), "started_at": time.time()}, ensure_ascii=False)
        for attempt in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                self.acquired = True
                return self
            except FileExistsError:
                if attempt == 0 and self._is_stale():
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise RuntimeError(f"已有 Agent 实例正在运行（锁文件：{self.path}）")
        raise RuntimeError("无法获取 Agent 运行锁")

    def _is_stale(self) -> bool:
        pid = None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            started_at = float(data.get("started_at", 0))
            pid = int(data.get("pid", 0)) or None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            started_at = self.path.stat().st_mtime
        if time.time() - started_at <= self.stale_after_seconds:
            return False
        if pid:
            try:
                os.kill(pid, 0)
                return False
            except PermissionError:
                return False
            except OSError:
                pass
        return True

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self.acquired = False
