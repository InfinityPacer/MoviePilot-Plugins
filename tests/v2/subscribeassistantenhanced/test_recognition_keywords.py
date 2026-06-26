"""识别增强关键字配置测试。"""
import subscribeassistantenhanced.recognition as recognition
from subscribeassistantenhanced.shared.config import DEFAULT_RECOGNITION_GUARD_CUSTOM_CONFIG
from subscribeassistantenhanced.recognition.guard import RecognitionGuard
from subscribeassistantenhanced.recognition.keywords import (
    load_keyword_groups,
    match_first,
)
from subscribeassistantenhanced.recognition.strategy import (
    ACTION_CODES,
    parse_strategy,
)
from subscribeassistantenhanced.recognition.types import (
    ACTION_ALLOW,
    ACTION_BLOCK,
    ACTION_SOFT_BLOCK,
    BatchDecision,
    CandidateResource,
    Decision,
    RecognitionSettings,
)


def test_default_keyword_groups_do_not_include_old_weak_live_action_terms():
    groups = load_keyword_groups("")

    assert "主演" not in groups.live_action
    assert "演员" not in groups.live_action
    assert "古装" not in groups.live_action
    assert "真人版" in groups.live_action
    assert "电视剧版" in groups.live_action


def test_load_keyword_groups_normalizes_user_rule_groups():
    groups = load_keyword_groups("""
live_action:
  - 真人版
animation: 动画
movie:
  - 电影版
tv: S01
allow: 官方合集
block:
  - 错误作品
hard_block:
  - 强制错误
""")

    assert groups.live_action == ["真人版"]
    assert groups.animation == ["动画"]
    assert groups.movie == ["电影版"]
    assert groups.tv == ["S01"]
    assert groups.allow == ["官方合集"]
    assert groups.block == ["错误作品"]
    assert groups.hard_block == ["强制错误"]


def test_invalid_yaml_fails_open_to_safe_default_groups():
    groups = load_keyword_groups(": bad: yaml")

    assert groups.live_action == ["电视剧版", "真人版", "实拍版", "真人剧"]
    assert groups.allow == []
    assert groups.block == []
    assert groups.hard_block == []


def test_invalid_regex_is_ignored_without_blocking_other_patterns():
    assert match_first(["(", "真人版"], "凡人修仙传 真人版") == "真人版"


def test_default_strategy_inputs_parse_without_warnings():
    for text in ("", "# only comments\n", "actions:\nempty_pool:\nkeywords:\n",
                 DEFAULT_RECOGNITION_GUARD_CUSTOM_CONFIG):
        strategy = parse_strategy("balanced", text)

        assert strategy.warnings == set()
        assert strategy.action_for("missing_year") == "observe"
        assert strategy.action_for("target_range_oversized") == "soft_block"
        assert strategy.empty_pool_policy == "recover_soft_block"
        assert strategy.keyword_groups.live_action == ["电视剧版", "真人版", "实拍版", "真人剧"]


def test_strategy_merges_actions_empty_pool_and_keywords():
    strategy = parse_strategy("balanced", """
actions:
  missing_year: block
  target_range_oversized: inherit
  user_block: observe
empty_pool:
  policy: never_recover
  non_recoverable_codes:
    - target_range_oversized
keywords:
  allow:
    - 私有站点TOKEN_SECRET
  live_action:
    - 真人版
""")

    assert strategy.action_for("missing_year") == "block"
    assert strategy.action_for("target_range_oversized") == "soft_block"
    assert strategy.action_for("user_block") == "observe"
    assert strategy.empty_pool_policy == "never_recover"
    assert strategy.non_recoverable_codes == {"target_range_oversized"}
    assert strategy.keyword_groups.allow == ["私有站点TOKEN_SECRET"]
    assert strategy.keyword_groups.live_action == ["真人版"]
    assert strategy.warnings == set()


def test_strategy_warning_codes_are_stable_and_localized():
    strategy = parse_strategy("balanced", """
unknown_root: true
actions:
  missing_year: drop
  unknown_code: block
empty_pool:
  policy: maybe
  non_recoverable_codes: target_range_oversized
keywords:
  allow: token=PRIVATE
  block: 123
  hard_block:
    - "("
""")

    assert {
        "unknown_strategy_key",
        "unknown_action_code",
        "invalid_action_value",
        "invalid_empty_pool_policy",
        "invalid_non_recoverable_codes_type",
        "invalid_keyword_group_type",
        "invalid_keyword_regex",
    }.issubset(strategy.warnings)
    assert strategy.action_for("missing_year") == "observe"
    assert strategy.empty_pool_policy == "recover_soft_block"
    assert strategy.keyword_groups.allow == []
    assert strategy.keyword_groups.block == []
    assert strategy.keyword_groups.hard_block == []


def test_invalid_builtin_keyword_group_type_keeps_default_group():
    strategy = parse_strategy("balanced", """
keywords:
  live_action: 真人版
""")

    assert strategy.warnings == {"invalid_keyword_group_type"}
    assert strategy.keyword_groups.live_action == ["电视剧版", "真人版", "实拍版", "真人剧"]
    assert "keywords=live_action" not in strategy.summary


def test_unknown_non_recoverable_code_warns_without_dropping_valid_codes():
    strategy = parse_strategy("balanced", """
empty_pool:
  non_recoverable_codes:
    - target_range_oversized
    - unknown_code
""")

    assert strategy.warnings == {"unknown_non_recoverable_code"}
    assert strategy.non_recoverable_codes == {"target_range_oversized"}


def test_strategy_rejects_bad_yaml_root_and_group_types():
    invalid_yaml = parse_strategy("balanced", ": bad: yaml")
    non_mapping = parse_strategy("balanced", "- item")
    invalid_groups = parse_strategy("strict", """
actions: []
empty_pool: []
keywords: []
""")

    assert invalid_yaml.warnings == {"invalid_yaml"}
    assert non_mapping.warnings == {"non_mapping_yaml"}
    assert invalid_groups.warnings == {
        "invalid_actions_type",
        "invalid_empty_pool_type",
        "invalid_keywords_type",
    }
    assert invalid_groups.empty_pool_policy == "never_recover"


def test_strategy_summary_is_privacy_safe():
    strategy = parse_strategy("balanced", """
actions:
  missing_year: block
empty_pool:
  policy: recover_soft_block
  non_recoverable_codes:
    - missing_year
keywords:
  allow:
    - 私有站点 token=SECRET
""")

    summary = strategy.summary

    assert "missing_year" in summary
    assert "policy=recover_soft_block" in summary
    assert "keywords=allow" in summary
    assert "hash=" in summary
    assert "SECRET" not in summary
    assert "私有站点" not in summary
    assert "token=" not in summary


def test_strategy_supported_action_codes_are_explicit():
    assert ACTION_CODES == {
        "missing_year",
        "target_range_oversized",
        "user_block",
        "secondary_identity_conflict",
    }


def test_recognition_types_keep_identity_and_batch_contracts():
    candidate = CandidateResource(
        explicit_tmdb_id=100,
        explicit_douban_id="db100",
        recognized_tmdb_id=200,
        recognized_douban_id="db200",
        candidate_recognized=True,
        match_source="tmdbid",
        media_info_is_target=False,
    )
    decision = Decision(action=ACTION_ALLOW, final_action=ACTION_SOFT_BLOCK, candidate=candidate)
    batch = BatchDecision(
        selection_original_count=3,
        recognition_input_count=2,
        recognition_evaluated_count=2,
        recognition_output_count=1,
        final_count=1,
        decisions=[decision],
    )

    assert candidate.explicit_tmdb_id == 100
    assert candidate.recognized_tmdb_id == 200
    assert decision.removed is True
    assert Decision(action=ACTION_BLOCK, final_action=ACTION_ALLOW).removed is False
    assert batch.selection_original_count == 3
    assert batch.recognition_evaluated_count == 2
    assert batch.final_count == 1


def test_recognition_package_exports_public_symbols():
    assert recognition.RecognitionSettings is RecognitionSettings
    assert recognition.RecognitionGuard is RecognitionGuard
    assert recognition.__all__ == ["RecognitionSettings", "RecognitionRuntime", "RecognitionGuard"]
