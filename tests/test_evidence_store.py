import json
import tempfile
import unittest
from pathlib import Path

from evidence_store import EvidenceStore, sha256_file


class EvidenceStoreTests(unittest.TestCase):
    def test_run_artifacts_are_hashed_and_write_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            run_id = "20260831T010203000000Z-test0001"
            url = "https://example.com/pricing"
            store.begin_run(run_id, [url])
            store.record_crawl(run_id, url, content="套餐价格 99 元")
            store.record_analysis(run_id, url, {"mode": "baseline", "verified": True})
            with self.assertRaises(FileExistsError):
                store.record_analysis(run_id, url, {"mode": "overwrite"})

            manifest_path = store.finalize_run(run_id)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifact = next(item for item in manifest["files"] if item["path"].endswith("raw.md"))
            raw_path = manifest_path.parent / artifact["path"]
            self.assertEqual(artifact["sha256"], sha256_file(raw_path))
            latest = json.loads(store.latest_index.read_text(encoding="utf-8"))
            self.assertEqual(latest["run_id"], run_id)
            self.assertEqual(latest["manifest_sha256"], sha256_file(manifest_path))

    def test_retention_is_disabled_without_positive_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            for index in range(3):
                run_id = f"20260831T01020{index}000000Z-test000{index}"
                store.begin_run(run_id, [])
                store.finalize_run(run_id)
            self.assertEqual(store.prune_runs(), [])
            self.assertEqual(len(list((Path(directory) / "runs").iterdir())), 3)
            removed = store.prune_runs(max_runs=2)
            self.assertEqual(len(removed), 1)
            self.assertEqual(len(list((Path(directory) / "runs").iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
