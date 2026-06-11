"""best_version/converter.py 分集→全集转换单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.best_version.converter import BestVersionConverter


class TestConvertToFull:

    def test_success(self):
        oper = MagicMock()
        conv = BestVersionConverter(subscribe_oper=oper)
        sub = SimpleNamespace(id=1)
        assert conv.convert_to_full(sub) is True
        oper.update.assert_called_once()
        assert oper.update.call_args.args[0] == 1
        payload = oper.update.call_args.args[1]
        assert payload["best_version_full"] == 1
        assert payload["last_update"]

    def test_failure_keeps_original(self):
        oper = MagicMock()
        oper.update.side_effect = Exception("DB error")
        conv = BestVersionConverter(subscribe_oper=oper)
        sub = SimpleNamespace(id=1)
        assert conv.convert_to_full(sub) is False

    def test_no_oper_returns_false(self):
        conv = BestVersionConverter(subscribe_oper=None)
        sub = SimpleNamespace(id=1)
        assert conv.convert_to_full(sub) is False

    def test_no_id_returns_false(self):
        conv = BestVersionConverter(subscribe_oper=MagicMock())
        sub = SimpleNamespace(id=0)
        assert conv.convert_to_full(sub) is False
