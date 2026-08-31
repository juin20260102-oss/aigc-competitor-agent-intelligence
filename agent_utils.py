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
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit


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
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_SPACE_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_RE = re.compile(r"\n{3,}")
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "ref", "referrer", "source", "trace"}


def _normalized_link(match: re.Match[str]) -> str:
    label, target = match.groups()
    parsed = urlsplit(target.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return f"[{label}]({target.strip()})"
    query = sorted(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
        ]
    )
    canonical = urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", urlencode(query), "")
    )
    return f"[{label}]({canonical})"


def normalize_content(content: str) -> str:
    """Reduce crawler noise while preserving wording, prices, and link destinations."""
    text = content.replace("\ufeff", "").replace("\u200b", "")
    text = _IMAGE_RE.sub(lambda match: match.group(1), text)
    text = _LINK_RE.sub(_normalized_link, text)
    normalized_lines = []
    for raw_line in text.splitlines():
        line = _SPACE_RE.sub(" ", raw_line).strip()
        if line:
            normalized_lines.append(line)
    return _BLANK_RE.sub("\n\n", "\n".join(normalized_lines)).strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()


def legacy_site_key_for_url(url: str) -> str:
    clean = re.sub(r"^https?://", "", url).rstrip("/")
    return re.sub(r"[^\w\-.]", "_", clean)


def site_key_for_url(url: str, *, max_length: int = 120) -> str:
    """Return a bounded, collision-resistant key while retaining a readable prefix."""
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "unknown").encode("idna").decode("ascii").lower()
    port = f"-{parsed.port}" if parsed.port else ""
    identity = urlunsplit((parsed.scheme.lower(), f"{host}{port}", parsed.path or "/", parsed.query, ""))
    readable = re.sub(r"[^a-zA-Z0-9.-]+", "_", f"{host}{port}{parsed.path}").strip("_.-")
    readable = readable or "site"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    prefix_length = max(1, max_length - len(digest) - 2)
    return f"{readable[:prefix_length]}--{digest}"


def site_key_candidates(url: str) -> tuple[str, ...]:
    """Return the current key followed by legacy aliases for read compatibility."""
    current = site_key_for_url(url)
    legacy = legacy_site_key_for_url(url)
    return (current,) if current == legacy else (current, legacy)


def resolve_site_artifact(
    runtime_dir: str | Path,
    demo_dir: str | Path,
    url: str,
    suffix: str,
    *,
    migrate_legacy: bool = True,
) -> Path | None:
    """Resolve a current/legacy artifact and copy runtime legacy data to the new key."""
    runtime = Path(runtime_dir)
    demo = Path(demo_dir)
    current, *aliases = site_key_candidates(url)
    target = runtime / f"{current}{suffix}"
    if target.exists():
        return target
    for key in (*aliases, current):
        candidate = runtime / f"{key}{suffix}"
        if candidate.exists():
            if migrate_legacy and key != current:
                atomic_write_bytes(target, candidate.read_bytes())
                return target
            return candidate
    for key in (current, *aliases):
        candidate = demo / f"{key}{suffix}"
        if candidate.exists():
            return candidate
    return None


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

    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=True)
    changed_fragments = []
    change_contexts = []
    diff_parts = ["--- previous", "+++ current"]
    changed_characters = 0
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        old_block = "\n".join(old_lines[old_start:old_end])
        new_block = "\n".join(new_lines[new_start:new_end])
        prefix = os.path.commonprefix((old_block, new_block))
        old_tail = old_block[len(prefix) :]
        new_tail = new_block[len(prefix) :]
        suffix = os.path.commonprefix((old_tail[::-1], new_tail[::-1]))[::-1]
        if suffix:
            old_changed = old_tail[: -len(suffix)]
            new_changed = new_tail[: -len(suffix)]
        else:
            old_changed, new_changed = old_tail, new_tail
        changed_characters += max(len(old_changed), len(new_changed))
        changed_fragments.extend((old_changed, new_changed))
        nearby = (prefix[-80:] + old_changed + new_changed + suffix[:80])
        change_contexts.append(nearby)
        if old_changed:
            diff_parts.append(f"- {(prefix[-160:] + old_changed + suffix[:160])[:1200]}")
        if new_changed:
            diff_parts.append(f"+ {(prefix[-160:] + new_changed + suffix[:160])[:1200]}")

    document_length = max(len(old), len(new), 1)
    relative_change = changed_characters / document_length
    similarity = max(0.0, 1.0 - relative_change)
    diff_context = "\n".join(diff_parts)
    fragment_text = " ".join(changed_fragments).strip()
    context_text = " ".join(change_contexts)
    numeric_only_change = bool(fragment_text) and not re.search(r"[^\W\d_]", fragment_text)
    if numeric_only_change:
        signal_pattern = r"价格|定价|套餐|折扣|积分|额度|版本|元|¥|￥|%"
    else:
        signal_pattern = r"价格|定价|套餐|免费|折扣|积分|额度|版本|上线|发布|新增|下线|功能|API|模型|https?://"
    high_signal = bool(re.search(signal_pattern, context_text, flags=re.IGNORECASE))
    changed = (
        changed_characters >= min_changed_characters and relative_change >= min_change_ratio
    ) or (high_signal and changed_characters >= 1)
    if len(diff_context) > max_diff_characters:
        marker = "\n...（中间差异内容已截断）...\n"
        side = max(1, (max_diff_characters - len(marker)) // 2)
        diff_context = diff_context[:side] + marker + diff_context[-side:]
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


DEFAULT_MODEL_BASE_URLS = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "https://api.openai.com/v1",
)


def allowed_model_base_urls() -> tuple[str, ...]:
    configured = os.getenv("MODEL_BASE_URL_ALLOWLIST", "")
    values = [item.strip().rstrip("/") for item in configured.split(",") if item.strip()]
    return tuple(dict.fromkeys(values or DEFAULT_MODEL_BASE_URLS))


def validate_model_base_url(url: str, *, allowed: tuple[str, ...] | None = None) -> str:
    candidate = ensure_single_line(url, "Base URL").rstrip("/")
    parsed = urlsplit(candidate)
    is_loopback_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme != "https" and not is_loopback_http:
        raise ValueError("模型 Base URL 必须使用 HTTPS；仅显式允许本机 HTTP 服务")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("模型 Base URL 格式无效，不允许凭据、查询参数或片段")
    approved = tuple(item.rstrip("/") for item in (allowed or allowed_model_base_urls()))
    if candidate not in approved:
        raise ValueError("模型 Base URL 不在 MODEL_BASE_URL_ALLOWLIST 中")
    if not is_loopback_http:
        validate_public_http_url(candidate)
    return candidate


def validate_wecom_webhook(url: str) -> str:
    candidate = ensure_single_line(url, "Webhook")
    parsed = urlsplit(candidate)
    if parsed.scheme != "https" or parsed.hostname != "qyapi.weixin.qq.com":
        raise ValueError("企业微信 Webhook 必须使用 qyapi.weixin.qq.com 的 HTTPS 地址")
    if parsed.path != "/cgi-bin/webhook/send" or not parse_qs(parsed.query).get("key"):
        raise ValueError("企业微信 Webhook 路径或 key 参数无效")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Webhook 不允许包含凭据或片段")
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
