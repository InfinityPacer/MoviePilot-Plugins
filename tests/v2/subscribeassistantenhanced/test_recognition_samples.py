"""识别增强历史样本回放测试。"""
from subscribeassistantenhanced.recognition.guard import RecognitionGuard
from subscribeassistantenhanced.recognition.types import RecognitionSettings


def _guard(mode="balanced"):
    return RecognitionGuard(RecognitionSettings(mode=mode))


def test_animation_candidate_with_actor_and_costume_is_not_blocked():
    decision = _guard().evaluate_dicts(
        {
            "name": "牧神记",
            "media_type": "电视剧",
            "shape": "animation",
            "target_episodes": [82],
            "range_confidence": "high",
        },
        {
            "title": "牧神记 第82集",
            "description": "类型: 动作/动画/奇幻/古装 主演: 配音演员",
            "episodes": [82],
        },
    )

    assert decision.final_action in {"allow", "observe"}
    assert decision.code != "animation_live_action_conflict"


def test_ever_night_full_60_covering_target_range_soft_blocks_as_oversized_pack():
    decision = _guard().evaluate_dicts(
        {
            "name": "将夜",
            "media_type": "电视剧",
            "shape": "animation",
            "target_episodes": list(range(8, 20)),
            "range_confidence": "high",
        },
        {"title": "Ever Night S01 全60集", "description": "将夜 全60集", "episodes": list(range(1, 61))},
    )

    assert decision.final_action == "soft_block"
    assert decision.code == "target_range_oversized"


def test_candidate_range_disjoint_from_target_blocks():
    decision = _guard().evaluate_dicts(
        {
            "name": "将夜",
            "media_type": "电视剧",
            "shape": "animation",
            "target_episodes": list(range(8, 20)),
            "range_confidence": "high",
        },
        {
            "title": "Ever Night S01 E40-E60",
            "description": "将夜 E40-E60",
            "episodes": list(range(40, 61)),
        },
    )

    assert decision.final_action == "block"
    assert decision.code == "target_range_not_covered"


def test_s00_candidate_covering_requested_special_observes_not_blocks():
    decision = _guard().evaluate_dicts(
        {
            "name": "灵笼",
            "media_type": "电视剧",
            "shape": "animation",
            "season": 0,
            "target_episodes": [7],
            "range_confidence": "high",
        },
        {"title": "灵笼 S00E07", "description": "特别篇", "episodes": [7]},
    )

    assert decision.final_action in {"allow", "observe"}
    assert decision.code != "target_range_not_covered"


def test_episode_group_unavailable_fails_open_for_range_veto():
    decision = _guard().evaluate_dicts(
        {
            "name": "测试剧",
            "media_type": "电视剧",
            "episode_group": "eg-1",
            "target_episodes": [],
            "range_confidence": "unknown",
        },
        {"title": "测试剧 SP01", "description": "特别篇", "episodes": [1]},
    )

    assert decision.final_action == "fail_open"
    assert decision.code == "target_range_unknown"


def test_big_brother_secondary_mismatch_with_chinese_alias_observes():
    decision = _guard().evaluate_dicts(
        {
            "name": "师兄啊师兄",
            "media_type": "电视剧",
            "tmdb_id": 218642,
            "aliases": ["师兄啊师兄"],
            "target_episodes": [40],
            "range_confidence": "high",
        },
        {
            "title": "Big Brother S01E40",
            "description": "师兄啊师兄 动画",
            "episodes": [40],
            "secondary_tmdb_id": 237243,
        },
    )

    assert decision.final_action == "observe"
    assert decision.code == "secondary_identity_conflict_with_alias"


def test_live_action_drama_version_blocks_animation_target():
    decision = _guard().evaluate_dicts(
        {
            "name": "凡人修仙传",
            "media_type": "电视剧",
            "shape": "animation",
            "target_episodes": [1],
            "range_confidence": "high",
        },
        {"title": "凡人修仙传 电视剧版", "description": "真人剧", "episodes": [1]},
    )

    assert decision.final_action == "block"
    assert decision.code == "animation_live_action_conflict"


def test_explicit_tmdb_mismatch_blocks():
    decision = _guard().evaluate_dicts(
        {"name": "测试剧", "media_type": "电视剧", "tmdb_id": 100},
        {"title": "测试剧", "tmdb_id": 200},
    )

    assert decision.final_action == "block"
    assert decision.code == "tmdb_id_mismatch"
