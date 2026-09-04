from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import youtube_digest as yd

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 4, 12, 0, tzinfo=KST)


def make_video(**kwargs):
    """테스트용 영상 사전. 필요한 값만 덮어쓴다."""
    base = {
        "video_id": "abc123",
        "title": "테스트 영상",
        "channel": "테스트 채널",
        "published_at": "2026-09-03T11:00:00Z",
        "audio_language": "",
        "default_language": "",
        "view_count": 1000,
        "like_count": 10,
        "korean_ratio": 0.9,
        "url": "https://www.youtube.com/watch?v=abc123",
    }
    base.update(kwargs)
    return base


def test_korean_ratio_pure_korean() -> None:
    assert yd.korean_ratio("에이전트 만들기") == 1.0


def test_korean_ratio_pure_english() -> None:
    assert yd.korean_ratio("How to build an AI agent") == 0.0


def test_korean_ratio_mixed() -> None:
    ratio = yd.korean_ratio("AI 에이전트")
    assert 0.0 < ratio < 1.0


def test_korean_ratio_ignores_punctuation() -> None:
    """기호와 공백은 비율 계산에서 제외된다."""
    assert yd.korean_ratio("!!! 한글 !!!") == 1.0


def test_korean_ratio_empty() -> None:
    assert yd.korean_ratio("") == 0.0
    assert yd.korean_ratio("!!!???") == 0.0


def test_classify_korean_by_language_tag() -> None:
    """언어 태그가 ko면 한글 비율이 낮아도 한국어로 본다."""
    video = make_video(audio_language="ko", korean_ratio=0.0)
    assert yd.classify(video, NOW, 7) == "korean"


def test_classify_korean_by_ratio() -> None:
    video = make_video(korean_ratio=0.5)
    assert yd.classify(video, NOW, 7) == "korean"


def test_classify_unsure() -> None:
    video = make_video(korean_ratio=0.2)
    assert yd.classify(video, NOW, 7) == "unsure"


def test_classify_skip_english() -> None:
    video = make_video(korean_ratio=0.05)
    assert yd.classify(video, NOW, 7) == "skip"


def test_classify_skip_too_old() -> None:
    """7일보다 오래된 영상은 한국어여도 제외된다."""
    video = make_video(published_at="2026-08-20T11:00:00Z", audio_language="ko")
    assert yd.classify(video, NOW, 7) == "skip"


def test_classify_boundary_is_inclusive() -> None:
    """정확히 경계에 있는 영상은 포함된다."""
    video = make_video(published_at="2026-08-28T12:00:00Z", audio_language="ko")
    assert yd.classify(video, NOW, 7) == "korean"


def test_limit_per_channel_caps() -> None:
    videos = [
        make_video(video_id="a", channel="X"),
        make_video(video_id="b", channel="X"),
        make_video(video_id="c", channel="X"),
        make_video(video_id="d", channel="Y"),
    ]
    kept = yd.limit_per_channel(videos, 2)
    assert [v["video_id"] for v in kept] == ["a", "b", "d"]


def test_limit_per_channel_keeps_order() -> None:
    """입력 순서가 유지되어야 조회수 정렬 결과가 보존된다."""
    videos = [
        make_video(video_id="a", channel="X"),
        make_video(video_id="b", channel="Y"),
        make_video(video_id="c", channel="X"),
    ]
    kept = yd.limit_per_channel(videos, 1)
    assert [v["video_id"] for v in kept] == ["a", "b"]


def test_published_kst_converts_timezone() -> None:
    """UTC 01:00은 KST 10:00이다."""
    dt = yd.published_kst("2026-09-04T01:00:00Z")
    assert dt is not None
    assert dt.hour == 10


def test_published_kst_handles_bad_input() -> None:
    assert yd.published_kst("") is None
    assert yd.published_kst("not-a-date") is None
