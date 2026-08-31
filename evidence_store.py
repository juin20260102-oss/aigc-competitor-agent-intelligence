"""Immutable per-run evidence storage with hashes, indexing, migration, and retention."""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from agent_utils import atomic_write_bytes, atomic_write_json, atomic_write_text, normalize_content, site_key_for_url


def new_run_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EvidenceStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.runs_dir = self.root / "runs"
        self.latest_index = self.root / "data" / "latest_run.json"

    def run_dir(self, run_id: str) -> Path:
        if not re_full_run_id(run_id):
            raise ValueError("无效的 run_id")
        return self.runs_dir / run_id

    def begin_run(self, run_id: str, urls: list[str]) -> Path:
        directory = self.run_dir(run_id)
        directory.mkdir(parents=True, exist_ok=False)
        self._write_once(
            directory / "run_start.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "urls": urls,
            },
        )
        return directory

    def record_crawl(
        self,
        run_id: str,
        url: str,
        *,
        content: str | None,
        screenshot_path: str | Path | None = None,
        error: str | None = None,
    ) -> None:
        site_dir = self.run_dir(run_id) / site_key_for_url(url)
        site_dir.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, dict[str, object]] = {}
        if content is not None:
            raw_path = site_dir / "raw.md"
            normalized_path = site_dir / "normalized.txt"
            self._write_text_once(raw_path, content)
            self._write_text_once(normalized_path, normalize_content(content))
            artifacts["raw.md"] = self._artifact_info(raw_path)
            artifacts["normalized.txt"] = self._artifact_info(normalized_path)
        if screenshot_path and Path(screenshot_path).exists():
            screenshot = site_dir / "screenshot.png"
            self._write_bytes_once(screenshot, Path(screenshot_path).read_bytes())
            artifacts["screenshot.png"] = self._artifact_info(screenshot)
        self._write_once(
            site_dir / "crawl.json",
            {
                "url": url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "status": "success" if content is not None else "failed",
                "error": error,
                "artifacts": artifacts,
            },
        )

    def record_analysis(self, run_id: str, url: str, analysis: dict) -> None:
        site_dir = self.run_dir(run_id) / site_key_for_url(url)
        site_dir.mkdir(parents=True, exist_ok=True)
        self._write_once(site_dir / "analysis.json", analysis)

    def record_run_summary(self, run_id: str, summary: dict) -> None:
        self._write_once(self.run_dir(run_id) / "run_summary.json", summary)

    def finalize_run(
        self,
        run_id: str,
        *,
        report_path: str | Path | None = None,
        update_latest: bool = True,
    ) -> Path:
        directory = self.run_dir(run_id)
        if report_path and Path(report_path).exists():
            self._write_bytes_once(directory / "report.md", Path(report_path).read_bytes())
        files = []
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                files.append(
                    {
                        "path": path.relative_to(directory).as_posix(),
                        **self._artifact_info(path),
                    }
                )
        manifest = directory / "manifest.json"
        self._write_once(
            manifest,
            {
                "schema_version": 1,
                "run_id": run_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "files": files,
            },
        )
        if update_latest:
            atomic_write_json(
                self.latest_index,
                {
                    "run_id": run_id,
                    "manifest": str(manifest.relative_to(self.root)).replace("\\", "/"),
                    "manifest_sha256": sha256_file(manifest),
                },
            )
        return manifest

    def prune_runs(self, *, retention_days: int = 0, max_runs: int = 0) -> list[str]:
        """Remove finalized runs only when an explicit positive policy is configured."""
        if retention_days <= 0 and max_runs <= 0:
            return []
        runs = sorted(
            (path for path in self.runs_dir.glob("*") if (path / "manifest.json").exists()),
            key=lambda path: path.name,
            reverse=True,
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days) if retention_days > 0 else None
        removed = []
        for index, path in enumerate(runs):
            too_many = max_runs > 0 and index >= max_runs
            too_old = False
            if cutoff:
                completed = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                too_old = completed < cutoff
            if too_many or too_old:
                shutil.rmtree(path)
                removed.append(path.name)
        return removed

    @staticmethod
    def _artifact_info(path: Path) -> dict[str, object]:
        return {"sha256": sha256_file(path), "bytes": path.stat().st_size}

    @staticmethod
    def _write_once(path: Path, payload: object) -> None:
        if path.exists():
            raise FileExistsError(f"不可变证据已存在：{path}")
        atomic_write_json(path, payload)

    @staticmethod
    def _write_text_once(path: Path, content: str) -> None:
        if path.exists():
            raise FileExistsError(f"不可变证据已存在：{path}")
        atomic_write_text(path, content)

    @staticmethod
    def _write_bytes_once(path: Path, content: bytes) -> None:
        if path.exists():
            raise FileExistsError(f"不可变证据已存在：{path}")
        atomic_write_bytes(path, content)


def re_full_run_id(value: str) -> bool:
    return bool(value) and len(value) <= 64 and all(char.isalnum() or char in "-_" for char in value)


def configured_retention_policy() -> tuple[int, int]:
    def positive_int(name: str) -> int:
        raw = os.getenv(name, "0").strip()
        try:
            return max(0, int(raw))
        except ValueError:
            return 0

    return positive_int("EVIDENCE_RETENTION_DAYS"), positive_int("EVIDENCE_MAX_RUNS")
