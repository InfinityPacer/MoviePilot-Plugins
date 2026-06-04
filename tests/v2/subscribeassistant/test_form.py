"""
SubscribeAssistant 表单生成与配置解析辅助单测。

覆盖业务域：
- 表单生成：get_form / __get_recognition_guard_form 及子辅助
- 配置解析：__get_float_config / __get_int_config / __get_bool_config /
  __normalize_recognition_guard_notify / __get_default_recognition_guard_keyword_config
- 日志辅助：__truncate_log_value / __format_log_title_desc
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistant import SubscribeAssistant


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def make_plugin(**overrides) -> SubscribeAssistant:
    plugin = object.__new__(SubscribeAssistant)
    plugin.subscribe_oper = MagicMock()
    plugin.downloadhistory_oper = MagicMock()
    plugin.transferhistory_oper = MagicMock()
    plugin.tmdb_chain = MagicMock()
    plugin.downloader_helper = MagicMock()
    plugin._notify = False
    plugin._recognition_guard_keyword_config = None
    for k, v in overrides.items():
        setattr(plugin, k, v)
    return plugin


# ===========================================================================
# get_form
# ===========================================================================

class TestGetForm:

    def test_returns_tuple(self):
        plugin = make_plugin()
        result = plugin.get_form()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_form_list(self):
        plugin = make_plugin()
        form_list, defaults = plugin.get_form()
        assert isinstance(form_list, list)
        assert len(form_list) > 0

    def test_defaults_dict(self):
        plugin = make_plugin()
        form_list, defaults = plugin.get_form()
        assert isinstance(defaults, dict)
        assert "enabled" in defaults or "auto_download_delete" in defaults
        assert "recognition_guard_mode" in defaults

    def test_defaults_contain_recognition_guard(self):
        plugin = make_plugin()
        _, defaults = plugin.get_form()
        assert "recognition_guard_mode" in defaults
        assert defaults["recognition_guard_mode"] == "off"

    def test_form_has_vform(self):
        plugin = make_plugin()
        form_list, _ = plugin.get_form()
        assert form_list[0]["component"] == "VForm"


# ===========================================================================
# __get_recognition_guard_form
# ===========================================================================

class TestGetRecognitionGuardForm:

    def test_returns_dict(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_recognition_guard_form()
        assert isinstance(result, dict)
        assert result["component"] == "VWindowItem"

    def test_has_content(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_recognition_guard_form()
        assert "content" in result
        assert len(result["content"]) > 0


# ===========================================================================
# __get_recognition_guard_alert
# ===========================================================================

class TestGetRecognitionGuardAlert:

    def _call(self, alert_type, text):
        return SubscribeAssistant._SubscribeAssistant__get_recognition_guard_alert(alert_type, text)

    def test_error_alert(self):
        result = self._call("error", "test message")
        assert result["component"] == "VRow"
        content = result["content"][0]["content"][0]
        assert content["component"] == "VAlert"
        assert content["props"]["type"] == "error"
        assert content["props"]["text"] == "test message"

    def test_info_alert(self):
        result = self._call("info", "info msg")
        content = result["content"][0]["content"][0]
        assert content["props"]["type"] == "info"


# ===========================================================================
# __get_recognition_guard_control_col
# ===========================================================================

class TestGetRecognitionGuardControlCol:

    def _call(self, component, md=3):
        return SubscribeAssistant._SubscribeAssistant__get_recognition_guard_control_col(component, md)

    def test_structure(self):
        comp = {"component": "VSwitch"}
        result = self._call(comp, md=4)
        assert result["component"] == "VCol"
        assert result["props"]["md"] == 4
        assert result["content"] == [comp]


# ===========================================================================
# __get_recognition_guard_select
# ===========================================================================

class TestGetRecognitionGuardSelect:

    def _call(self, *args):
        return SubscribeAssistant._SubscribeAssistant__get_recognition_guard_select(*args)

    def test_structure(self):
        items = [{"title": "A", "value": "a"}]
        result = self._call("model", "label", items, "hint text")
        assert result["component"] == "VSelect"
        assert result["props"]["model"] == "model"
        assert result["props"]["items"] == items


# ===========================================================================
# __get_recognition_guard_switch
# ===========================================================================

class TestGetRecognitionGuardSwitch:

    def _call(self, *args):
        return SubscribeAssistant._SubscribeAssistant__get_recognition_guard_switch(*args)

    def test_structure(self):
        result = self._call("model", "label", "hint")
        assert result["component"] == "VSwitch"
        assert result["props"]["model"] == "model"


# ===========================================================================
# __get_recognition_guard_text_field
# ===========================================================================

class TestGetRecognitionGuardTextField:

    def _call(self, *args):
        return SubscribeAssistant._SubscribeAssistant__get_recognition_guard_text_field(*args)

    def test_structure(self):
        result = self._call("model", "label", "hint")
        assert result["component"] == "VTextField"
        assert result["props"]["type"] == "number"


# ===========================================================================
# __get_recognition_guard_keyword_dialog
# ===========================================================================

class TestGetRecognitionGuardKeywordDialog:

    def test_structure(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_recognition_guard_keyword_dialog()
        assert result["component"] == "VDialog"


# ===========================================================================
# __get_recognition_guard_keyword_editor
# ===========================================================================

class TestGetRecognitionGuardKeywordEditor:

    def test_structure(self):
        result = SubscribeAssistant._SubscribeAssistant__get_recognition_guard_keyword_editor()
        assert result["component"] == "VRow"
        editor = result["content"][0]["content"][0]
        assert editor["component"] == "VAceEditor"
        assert editor["props"]["lang"] == "yaml"


# ===========================================================================
# __get_float_config
# ===========================================================================

class TestGetFloatConfig:

    def _call(self, config, key, default):
        return SubscribeAssistant._SubscribeAssistant__get_float_config(config, key, default)

    def test_normal(self):
        assert self._call({"k": "3.14"}, "k", 0) == 3.14

    def test_missing_key(self):
        assert self._call({}, "k", 5.0) == 5.0

    def test_invalid_value(self):
        assert self._call({"k": "abc"}, "k", 7.0) == 7.0

    def test_int_value(self):
        assert self._call({"k": 10}, "k", 0) == 10.0


# ===========================================================================
# __get_int_config
# ===========================================================================

class TestGetIntConfig:

    def _call(self, config, key, default):
        return SubscribeAssistant._SubscribeAssistant__get_int_config(config, key, default)

    def test_normal(self):
        assert self._call({"k": "42"}, "k", 0) == 42

    def test_float_input(self):
        assert self._call({"k": "3.7"}, "k", 0) == 3

    def test_missing_key(self):
        assert self._call({}, "k", 10) == 10

    def test_invalid_value(self):
        assert self._call({"k": "abc"}, "k", 5) == 5


# ===========================================================================
# __get_bool_config
# ===========================================================================

class TestGetBoolConfig:

    def _call(self, config, key, default):
        return SubscribeAssistant._SubscribeAssistant__get_bool_config(config, key, default)

    def test_bool_true(self):
        assert self._call({"k": True}, "k", False) is True

    def test_bool_false(self):
        assert self._call({"k": False}, "k", True) is False

    def test_string_true(self):
        assert self._call({"k": "true"}, "k", False) is True

    def test_string_yes(self):
        assert self._call({"k": "yes"}, "k", False) is True

    def test_string_on(self):
        assert self._call({"k": "on"}, "k", False) is True

    def test_string_1(self):
        assert self._call({"k": "1"}, "k", False) is True

    def test_string_guard(self):
        assert self._call({"k": "guard"}, "k", False) is True

    def test_string_false(self):
        assert self._call({"k": "false"}, "k", True) is False

    def test_string_random(self):
        assert self._call({"k": "random"}, "k", True) is False

    def test_int_truthy(self):
        assert self._call({"k": 1}, "k", False) is True

    def test_int_falsy(self):
        assert self._call({"k": 0}, "k", True) is False

    def test_missing_key(self):
        assert self._call({}, "k", True) is True


# ===========================================================================
# __normalize_recognition_guard_notify
# ===========================================================================

class TestNormalizeRecognitionGuardNotify:

    def _call(self, value):
        return SubscribeAssistant._SubscribeAssistant__normalize_recognition_guard_notify(value)

    def test_valid_values(self):
        assert self._call("off") == "off"
        assert self._call("summary") == "summary"
        assert self._call("detail") == "detail"
        assert self._call("all") == "all"

    def test_invalid_value(self):
        assert self._call("invalid") == "off"

    def test_none(self):
        assert self._call(None) == "off"

    def test_empty(self):
        assert self._call("") == "off"


# ===========================================================================
# __get_default_recognition_guard_keyword_config
# ===========================================================================

class TestGetDefaultRecognitionGuardKeywordConfig:

    def test_contains_live_action(self):
        result = SubscribeAssistant._SubscribeAssistant__get_default_recognition_guard_keyword_config()
        assert "live_action" in result

    def test_contains_animation(self):
        result = SubscribeAssistant._SubscribeAssistant__get_default_recognition_guard_keyword_config()
        assert "animation" in result

    def test_contains_movie(self):
        result = SubscribeAssistant._SubscribeAssistant__get_default_recognition_guard_keyword_config()
        assert "movie" in result

    def test_is_string(self):
        result = SubscribeAssistant._SubscribeAssistant__get_default_recognition_guard_keyword_config()
        assert isinstance(result, str)


# ===========================================================================
# __truncate_log_value
# ===========================================================================

class TestTruncateLogValue:

    def _call(self, value, max_length=160, middle=False):
        return SubscribeAssistant._SubscribeAssistant__truncate_log_value(value, max_length, middle)

    def test_none(self):
        assert self._call(None) == ""

    def test_short_text(self):
        assert self._call("short") == "short"

    def test_long_text_truncated(self):
        text = "a" * 200
        result = self._call(text, max_length=20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_middle_truncation(self):
        text = "a" * 200
        result = self._call(text, max_length=30, middle=True)
        assert "..." in result
        assert len(result) <= 30

    def test_non_string_value(self):
        assert self._call(12345) == "12345"


# ===========================================================================
# __format_log_title_desc
# ===========================================================================

class TestFormatLogTitleDesc:

    def test_both_present(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__format_log_title_desc("Title", "Description")
        assert "Title" in result
        assert "Description" in result

    def test_title_only(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__format_log_title_desc("Title", None)
        assert "Title" in result

    def test_description_only(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__format_log_title_desc(None, "Desc")
        assert "Desc" in result

    def test_neither(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__format_log_title_desc(None, None)
        assert result == ""
