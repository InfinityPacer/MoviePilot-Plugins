from subscribeassistantenhanced import SubscribeAssistantEnhanced


def test_render_mode_uses_vue_assets():
    plugin = SubscribeAssistantEnhanced()

    assert plugin.get_render_mode() == ("vue", "dist/assets")


def test_summary_api_uses_bear_auth_and_coarse_payload_shape():
    plugin = SubscribeAssistantEnhanced()
    apis = plugin.get_api()

    summary_api = next(api for api in apis if api["path"] == "/summary")
    assert summary_api["auth"] == "bear"
    assert summary_api["methods"] == ["GET"]

    plugin.init_plugin({})
    payload = plugin._api_summary()

    assert set(payload) == {"domains", "pending_count", "monitored_torrents"}
    assert isinstance(payload["domains"], dict)
    assert isinstance(payload["pending_count"], int)
    assert isinstance(payload["monitored_torrents"], int)
