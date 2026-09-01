import tempfile
import unittest
from pathlib import Path

from r2_runtime_sync import R2RuntimeSync, safe_relative_path


class FakeResponse:
    def __init__(self, status_code=200, content=b"", payload=None):
        self.status_code = status_code
        self.content = content
        self.payload = payload or {"success": True}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.objects = {}

    def get(self, url):
        key = url.rsplit("/objects/", 1)[1]
        content = self.objects.get(key)
        return FakeResponse(404) if content is None else FakeResponse(content=content)

    def put(self, url, content, headers):
        self.objects[url.rsplit("/objects/", 1)[1]] = content
        return FakeResponse()

    def close(self):
        pass


class R2RuntimeSyncTests(unittest.TestCase):
    def make_sync(self):
        sync = R2RuntimeSync(account_id="account", token="token", bucket="bucket", prefix="prefix")
        sync.client = FakeClient()
        return sync

    def test_push_then_pull_verifies_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            source_path = Path(source)
            (source_path / "data").mkdir()
            (source_path / "data" / "snapshot.json").write_text('{"ok": true}', encoding="utf-8")
            sync = self.make_sync()
            self.assertEqual(sync.push(source_path), 1)
            self.assertEqual(sync.pull(Path(target)), 1)
            self.assertEqual(
                (Path(target) / "data" / "snapshot.json").read_text(encoding="utf-8"),
                '{"ok": true}',
            )

    def test_pull_rejects_tampered_object(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            source_path = Path(source)
            (source_path / "item.txt").write_text("safe", encoding="utf-8")
            sync = self.make_sync()
            sync.push(source_path)
            sync.client.objects["prefix/item.txt"] = b"tampered"
            with self.assertRaises(RuntimeError):
                sync.pull(Path(target))

    def test_rejects_path_traversal_from_manifest(self):
        with self.assertRaises(ValueError):
            safe_relative_path("../.env")


if __name__ == "__main__":
    unittest.main()
