"""shared/deletes.py DeletesStore 单测：删除指纹的归档与 enclosure/page_url 部分匹配。"""
from app.plugins.subscribeassistantenhanced.shared.deletes import DeletesStore


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

    def test_save_same_hash_merges_urls_and_identities_instead_of_overwriting(self):
        """同一哈希再次删除时保留此前记录的链接和资源身份，避免搜索与 RSS 互相覆盖。"""
        read, update, store = _store_mgr()
        ds = DeletesStore(read, update, identity_resolver=lambda _t: None)
        ds.save(
            {
                "hash": "3db38150daf7c83acf17bb413d9e29c3c8a90efd",
                "enclosure": "https://totheglory.im/rssdd.php?par=abc",
                "page_url": "https://totheglory.im/details.php?id=395931",
            },
            reason="manual",
        )
        ds.save(
            {
                "hash": "3DB38150DAF7C83ACF17BB413D9E29C3C8A90EFD",
                "enclosure": "https://totheglory.im/dl/395931/3576",
                "page_url": "https://totheglory.im/t/395931/",
            },
            reason="manual",
        )

        assert len(store["deletes"]) == 1
        assert ds.match(enclosure="https://totheglory.im/rssdd.php?par=abc") is True
        assert ds.match(page_url="https://totheglory.im/details.php?id=395931") is True
        assert ds.match(page_url="https://totheglory.im/t/395931/") is True

    def test_match_by_canonical_resource_identity_bridges_rss_and_search(self):
        """跨 RSS 与搜索链接格式完全不同时，按主程序规范化资源身份仍可命中，且不跨站误伤。"""
        from app.modules.indexer import IndexerModule

        read, update, _ = _store_mgr()
        ds = DeletesStore(read, update, identity_resolver=IndexerModule.torrent_resource_identity)
        ds.save(
            {
                "hash": "3db38150daf7c83acf17bb413d9e29c3c8a90efd",
                "site": 2,
                "enclosure": "https://totheglory.im/dl/395931/3576",
                "page_url": "https://totheglory.im/t/395931/",
            },
            reason="manual",
        )

        # TTG 两种 RSS（details.php?id= 与 rssdd.php?par=）均可直接命中
        assert ds.match(
            site=2,
            enclosure="https://totheglory.im/details.php?id=395931",
            page_url="https://totheglory.im/details.php?id=395931",
        ) is True
        assert ds.match(
            site=2,
            enclosure="https://totheglory.im/rssdd.php?par=dnZ2Mzk1OTMx&ssl=yes",
            page_url=None,
        ) is True
        # 不同站点同数字 ID 不能跨站误伤
        assert ds.match(
            site=8,
            enclosure="https://audiences.me/download.php?id=395931",
            page_url="https://audiences.me/details.php?id=395931",
        ) is False

    def test_match_by_real_hashes_covers_opaque_urls(self):
        """即使候选链接完全异构且无法提取资源 ID，提交前按真实 info_hash 仍必须命中。"""
        read, update, _ = _store_mgr()
        ds = DeletesStore(read, update, identity_resolver=lambda _t: None)
        ds.save(
            {
                "hash": "3db38150daf7c83acf17bb413d9e29c3c8a90efd",
                "enclosure": "https://site.example/opaque/first",
            },
            reason="manual",
        )

        assert ds.match(
            enclosure="https://site.example/opaque/completely-different",
            hashes=["3DB38150DAF7C83ACF17BB413D9E29C3C8A90EFD"],
        ) is True
        assert ds.match(
            enclosure="https://site.example/opaque/completely-different",
            hashes=["0000000000000000000000000000000000000000"],
        ) is False

    def test_match_accepts_torrent_info_and_handles_unconfigured_protocol_port(self):
        """传入 TorrentInfo 时自动提取站点与链接，且协议端口未装配时平滑回退 URL/hash 匹配。"""
        from types import SimpleNamespace

        read, update, _ = _store_mgr()
        ds = DeletesStore(read, update)
        assert ds.match(enclosure="https://example.test/a.torrent") is False

        ds.save(
            {
                "hash": "abc123",
                "site": 2,
                "site_name": "听听歌",
                "enclosure": "https://totheglory.im/dl/395931/3576",
                "page_url": "https://totheglory.im/t/395931/",
            },
            reason="manual",
        )
        candidate = SimpleNamespace(
            site=2,
            site_name="听听歌",
            enclosure="https://totheglory.im/dl/395931/9999",
            page_url="https://totheglory.im/t/395931/",
        )
        assert ds.match(torrent_info=candidate) is True
        assert ds.match(
            enclosure="https://totheglory.im/dl/395931/3576",
            partial=False,
        ) is True
        assert ds.match(
            enclosure="https://totheglory.im/dl/395931/9999",
            page_url="https://totheglory.im/t/999999/",
            partial=False,
        ) is False
