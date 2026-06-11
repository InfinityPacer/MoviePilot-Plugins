"""shared/deletes.py DeletesStore 单测：删除指纹的归档与 enclosure/page_url 部分匹配。"""
from subscribeassistantenhanced.shared.deletes import DeletesStore


def _store_mgr(store=None):
    store = store if store is not None else {}
    return (
        lambda key: store.get(key, {}),
        lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
        store,
    )


class TestDeletesStore:

    def test_save_records_fingerprint_by_hash(self):
        read, update, store = _store_mgr()
        ds = DeletesStore(read, update)
        ds.save({"hash": "h1", "enclosure": "http://x/t.torrent", "page_url": "http://x/p"},
                reason="timeout")
        entry = store["deletes"]["h1"]
        assert entry["enclosure"] == "http://x/t.torrent"
        assert entry["delete_type"] == "timeout"
        assert "delete_time" in entry

    def test_save_without_hash_is_noop(self):
        read, update, store = _store_mgr()
        DeletesStore(read, update).save({"enclosure": "x"})
        assert store.get("deletes", {}) == {}

    def test_match_by_enclosure_partial(self):
        read, update, _ = _store_mgr({"deletes": {"h1": {"enclosure": "http://x/t.torrent?passkey=abc"}}})
        assert DeletesStore(read, update).match(enclosure="http://x/t.torrent") is True

    def test_match_by_page_url(self):
        read, update, _ = _store_mgr({"deletes": {"h1": {"page_url": "http://site/details?id=5"}}})
        assert DeletesStore(read, update).match(page_url="http://site/details?id=5") is True

    def test_no_match_returns_false(self):
        read, update, _ = _store_mgr({"deletes": {"h1": {"enclosure": "http://x/a.torrent"}}})
        assert DeletesStore(read, update).match(
            enclosure="http://y/b.torrent", page_url="http://z/c") is False

    def test_cleanup_expired_removes_old_fingerprints(self):
        """超过保留期的删除指纹被清理，保留期内的保留（避免长期误杀同源资源）。"""
        import time
        now = time.time()
        read, update, store = _store_mgr({"deletes": {
            "old": {"hash": "old", "delete_time": now - 25 * 3600},
            "new": {"hash": "new", "delete_time": now - 2 * 3600},
        }})
        ds = DeletesStore(read, update)
        removed = ds.cleanup_expired(retention_hours=24, now=now)
        assert removed == 1
        assert "old" not in store["deletes"]
        assert "new" in store["deletes"]
