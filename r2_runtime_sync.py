"""Synchronize runtime evidence with private Cloudflare R2 using an API token."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx

from agent_utils import RUNTIME_ROOT, atomic_write_bytes


MANIFEST_NAME = "_runtime_sync_manifest.json"
DEFAULT_PREFIX = "aigc-competitor-agent/runtime"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_relative_path(value: str) -> Path:
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"R2 清单包含不安全路径：{value!r}")
    return Path(*candidate.parts)


class R2RuntimeSync:
    def __init__(self, *, account_id: str, token: str, bucket: str, prefix: str = DEFAULT_PREFIX):
        self.bucket = bucket.strip()
        self.prefix = prefix.strip("/")
        if not account_id.strip() or not token.strip() or not self.bucket:
            raise ValueError("需要 CLOUDFLARE_ACCOUNT_ID、CLOUDFLARE_API_TOKEN 和 R2_BUCKET")
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/r2/buckets/{self.bucket}/objects"
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {token}"}, timeout=httpx.Timeout(120.0)
        )

    def close(self) -> None:
        self.client.close()

    def _url(self, key: str) -> str:
        return f"{self.base_url}/{quote(key, safe='/')}"

    def get(self, key: str) -> bytes | None:
        response = self.client.get(self._url(key))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content

    def put(self, key: str, content: bytes, *, content_type: str = "application/octet-stream") -> None:
        response = self.client.put(
            self._url(key), content=content, headers={"Content-Type": content_type}
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(f"R2 上传失败：{payload.get('errors', payload)}")

    def pull(self, runtime_root: Path) -> int:
        manifest_content = self.get(f"{self.prefix}/{MANIFEST_NAME}")
        if manifest_content is None:
            print("R2 中尚无运行基线，将以仓库演示数据初始化。")
            return 0
        try:
            manifest = json.loads(manifest_content.decode("utf-8"))
            files = manifest["files"]
        except (UnicodeDecodeError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("R2 运行清单无效，已拒绝恢复") from exc
        if not isinstance(files, list):
            raise RuntimeError("R2 运行清单 files 必须为数组")

        restored = 0
        for item in files:
            if not isinstance(item, dict):
                raise RuntimeError("R2 运行清单包含无效条目")
            relative = safe_relative_path(str(item.get("path", "")))
            expected_hash = str(item.get("sha256", ""))
            content = self.get(f"{self.prefix}/{relative.as_posix()}")
            if content is None:
                raise RuntimeError(f"R2 缺少清单列出的文件：{relative.as_posix()}")
            if sha256_bytes(content) != expected_hash:
                raise RuntimeError(f"R2 文件哈希不匹配：{relative.as_posix()}")
            atomic_write_bytes(runtime_root / relative, content)
            restored += 1
        print(f"已从 R2 恢复 {restored} 个运行文件。")
        return restored

    def push(self, runtime_root: Path) -> int:
        if not runtime_root.exists():
            print("本次没有 runtime 目录可上传。")
            return 0
        files = []
        for path in sorted(runtime_root.rglob("*")):
            if not path.is_file() or path.name == ".agent-run.lock" or path.suffix == ".tmp":
                continue
            relative = path.relative_to(runtime_root)
            content = path.read_bytes()
            self.put(
                f"{self.prefix}/{relative.as_posix()}",
                content,
                content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
            files.append(
                {"path": relative.as_posix(), "sha256": sha256_bytes(content), "bytes": len(content)}
            )
        manifest = {"schema_version": 1, "files": files}
        self.put(
            f"{self.prefix}/{MANIFEST_NAME}",
            (json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"),
            content_type="application/json",
        )
        print(f"已上传 {len(files)} 个运行文件，并在最后提交同步清单。")
        return len(files)


def from_environment() -> R2RuntimeSync:
    return R2RuntimeSync(
        account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
        token=os.getenv("CLOUDFLARE_API_TOKEN", ""),
        bucket=os.getenv("R2_BUCKET", ""),
        prefix=os.getenv("R2_RUNTIME_PREFIX", DEFAULT_PREFIX),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=("pull", "push"))
    parser.add_argument("--runtime-dir", type=Path, default=RUNTIME_ROOT)
    args = parser.parse_args()
    sync = from_environment()
    try:
        if args.direction == "pull":
            sync.pull(args.runtime_dir)
        else:
            sync.push(args.runtime_dir)
    finally:
        sync.close()


if __name__ == "__main__":
    main()
