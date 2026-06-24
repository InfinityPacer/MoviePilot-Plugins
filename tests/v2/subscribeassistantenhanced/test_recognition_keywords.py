"""识别增强关键字配置测试。"""
import subscribeassistantenhanced.recognition as recognition
from subscribeassistantenhanced.recognition.guard import RecognitionGuard
from subscribeassistantenhanced.recognition.keywords import (
    load_keyword_groups,
    match_first,
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
