"""Copy legacy latest snapshots into a checksummed immutable evidence run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_utils import DEMO_DATA_DIR, PROJECT_ROOT, RUNTIME_ROOT, compact_error
from evidence_store import EvidenceStore, new_run_id

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def discover_snapshots(source: Path) -> list[tuple[Path, dict]]:
    discovered = []
    for path in sorted(source.glob("*_latest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[跳过] {path.name}：{compact_error(exc)}")
            continue
        if isinstance(payload, dict) and payload.get("url") and payload.get("content") is not None:
            discovered.append((path, payload))
    return discovered


def migrate(source: Path, store: EvidenceStore) -> tuple[str, int]:
    snapshots = discover_snapshots(source)
    if not snapshots:
        raise RuntimeError(f"未在 {source} 找到可迁移快照")
    run_id = "legacy-" + new_run_id()
    urls = [payload["url"] for _, payload in snapshots]
    store.begin_run(run_id, urls)
    for snapshot_path, payload in snapshots:
        screenshot = payload.get("screenshot_path")
        screenshot_path = PROJECT_ROOT / screenshot if screenshot else None
        store.record_crawl(
            run_id,
            payload["url"],
            content=payload.get("content", ""),
            screenshot_path=screenshot_path,
        )
        try:
            source_label = str(snapshot_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            source_label = str(snapshot_path.resolve())
        store.record_analysis(
            run_id,
            payload["url"],
            {
                "mode": "legacy_import",
                "source": source_label,
                "captured_at": payload.get("captured_at"),
                "profile": payload.get("profile"),
                "profile_analysis": payload.get("profile_analysis"),
                "update_history": payload.get("update_history", []),
            },
        )
    store.finalize_run(run_id, update_latest=False)
    return run_id, len(snapshots)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEMO_DATA_DIR / "snapshots")
    parser.add_argument("--apply", action="store_true", help="执行只复制、不删除的迁移")
    args = parser.parse_args()
    snapshots = discover_snapshots(args.source)
    if not args.apply:
        print(f"DRY-RUN：发现 {len(snapshots)} 个快照；加 --apply 后复制到 {RUNTIME_ROOT / 'runs'}")
        return
    run_id, count = migrate(args.source, EvidenceStore(RUNTIME_ROOT))
    print(f"迁移完成：{count} 个快照已复制并校验，run_id={run_id}；源文件未修改。")


if __name__ == "__main__":
    main()
