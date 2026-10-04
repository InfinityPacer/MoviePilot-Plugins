"""通过主程序 Plex 客户端和本地 HTTP 服务验证分页认证契约。"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from app.modules.plex.plex import Plex
from app.plugins.plexlocalization import PlexLocalization


@pytest.mark.parametrize("type_id,is_collection", [(1, False), (2, False), (18, True)])
def test_pagination_preserves_auth_and_filters(type_id, is_collection):
    """已认领的服务要求每页认证，普通条目过滤与合集分页同时保持有效。"""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            target = urlsplit(self.path)
            query = parse_qs(target.query)
            calls.append((target.path, query, dict(self.headers)))
            authenticated = self.headers.get("X-Plex-Token") == "test-plex-token"
            start = int(query.get("X-Plex-Container-Start", ["0"])[0])
            size = int(query.get("X-Plex-Container-Size", ["0"])[0])
            payload = json.dumps({"MediaContainer": {
                "offset": start,
                "totalSize": 502,
                "Metadata": [{"ratingKey": str(i)} for i in range(start, min(start + size, 502))],
            }}).encode()
            self.send_response(200 if authenticated else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        # 仅跳过 SDK 初始化探测，分页仍经过真实 Plex.get_data 和 RequestUtils。
        with patch("app.modules.plex.plex.PlexServer"):
            plex = Plex(host=f"http://127.0.0.1:{server.server_port}", token="test-plex-token")
        try:
            plugin = PlexLocalization()
            keys, status = plugin._PlexLocalization__list_rating_keys(
                plex=plex,
                library=SimpleNamespace(key=1, title="测试库"),
                type_id=type_id,
                is_collection=is_collection,
                added_time=123456,
            )
        finally:
            plex.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()

    assert status == "complete"
    assert keys == [str(i) for i in range(502)]
    assert len(calls) == 2
    for offset, (path, query, headers) in zip((0, 500), calls):
        assert path == f"/library/sections/1/{'collections' if is_collection else 'all'}"
        assert query["X-Plex-Container-Start"] == [str(offset)]
        assert query["X-Plex-Container-Size"] == ["500"]
        assert headers["X-Plex-Token"] == "test-plex-token"
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"
        if is_collection:
            assert "type" not in query
        else:
            assert query["type"] == [str(type_id)]
            assert query["addedAt>"] == ["123456"]
