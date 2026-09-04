"""저장된 YouTube 수집 원본을 읽어 조건에 맞는 영상을 골라 보고한다.

새 API 호출을 하지 않는다. data/raw 아래 저장된 videos.json만 읽는다.
이전 수집분이 있으면 조회수 변화를 함께 계산한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "youtube"
KST = timezone(timedelta(hours=9))

HANGUL_START = "\uac00"
HANGUL_END = "\ud7a3"


def korean_ratio(text: str) -> float:
    """글자 중 한글 음절이 차지하는 비율을 반환한다."""
    letters = [c for c in text if c.isalnum()]
    if not letters:
        return 0.0
    hangul = [c for c in letters if HANGUL_START <= c <= HANGUL_END]
    return len(hangul) / len(letters)


def run_dirs(topic: str) -> list[Path]:
    """해당 주제의 수집 폴더를 시간순으로 반환한다."""
    topic_dir = RAW_ROOT / topic
    if not topic_dir.is_dir():
        raise FileNotFoundError(f"수집 폴더가 없습니다: {topic_dir}")
    dirs = sorted(p for p in topic_dir.iterdir() if p.is_dir())
    if not dirs:
        raise FileNotFoundError(f"수집 결과가 없습니다: {topic_dir}")
    return dirs


def load_videos(run_dir: Path) -> dict[str, dict[str, Any]]:
    """videos.json을 읽어 videoId를 키로 하는 사전을 만든다."""
    path = run_dir / "videos.json"
    if not path.is_file():
        raise FileNotFoundError(f"videos.json이 없습니다: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}

    for item in payload.get("items", []):
        video_id = item.get("id")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        title = snippet.get("title", "")
        description = snippet.get("description", "")

        result[video_id] = {
            "video_id": video_id,
            "title": title,
            "channel": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
            "audio_language": snippet.get("defaultAudioLanguage", ""),
            "default_language": snippet.get("defaultLanguage", ""),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "korean_ratio": korean_ratio(f"{title} {description[:500]}"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }

    return result


def published_kst(iso_utc: str) -> datetime | None:
    """UTC ISO 문자열을 KST datetime으로 바꾼다."""
    if not iso_utc:
        return None
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(KST)


def classify(video: dict[str, Any], now: datetime, days: int) -> str:
    """영상을 korean / unsure / skip 으로 분류한다."""
    published = published_kst(video["published_at"])
    if published is None or published < now - timedelta(days=days):
        return "skip"

    lang = video["audio_language"] or video["default_language"]
    if lang.startswith("ko"):
        return "korean"
    if video["korean_ratio"] >= 0.30:
        return "korean"
    if video["korean_ratio"] >= 0.10:
        return "unsure"
    return "skip"


def limit_per_channel(videos: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """채널당 최대 cap개까지만 남긴다. 입력 순서를 유지한다."""
    counts: dict[str, int] = {}
    kept = []
    for video in videos:
        channel = video["channel"]
        if counts.get(channel, 0) >= cap:
            continue
        counts[channel] = counts.get(channel, 0) + 1
        kept.append(video)
    return kept


def format_report(
    *,
    topic: str,
    current_dir: Path,
    previous_dir: Path | None,
    picked: list[dict[str, Any]],
    unsure: list[dict[str, Any]],
    previous: dict[str, dict[str, Any]],
    days: int,
) -> str:
    lines: list[str] = []
    stamp = current_dir.name
    lines.append(f"[{topic}] 최근 {days}일 한국어 영상 {len(picked)}건")
    lines.append(f"수집 시점: {stamp}")

    if previous_dir is not None:
        lines.append(f"비교 대상: {previous_dir.name}")
    else:
        lines.append("비교 대상: 없음 (첫 수집)")

    lines.append("")

    for rank, video in enumerate(picked, start=1):
        published = published_kst(video["published_at"])
        date_text = published.strftime("%m-%d %H:%M") if published else "?"

        change = ""
        if video["video_id"] in previous:
            before = previous[video["video_id"]]["view_count"]
            diff = video["view_count"] - before
            change = f"  ({diff:+,})" if diff else "  (변화 없음)"
        elif previous_dir is not None:
            change = "  (신규)"

        lines.append(f"{rank}. {video['title']}")
        lines.append(f"   {video['channel']} · {date_text}")
        lines.append(f"   조회 {video['view_count']:,}{change}")
        lines.append(f"   {video['url']}")
        lines.append("")

    if unsure:
        lines.append(f"한국어 판정 애매 {len(unsure)}건")
        for video in unsure:
            lines.append(
                f"   · {video['title'][:50]} "
                f"(한글 {video['korean_ratio']:.0%})"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube 수집 결과 보고")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--per-channel", type=int, default=2)
    parser.add_argument(
        "--compare-with", default="previous",
        help="previous | none | 폴더 이름",
    )
    args = parser.parse_args()

    dirs = run_dirs(args.topic)
    current_dir = dirs[-1]
    current = load_videos(current_dir)

    previous_dir: Path | None = None
    previous: dict[str, dict[str, Any]] = {}

    if args.compare_with == "previous" and len(dirs) >= 2:
        previous_dir = dirs[-2]
    elif args.compare_with not in ("previous", "none"):
        candidate = RAW_ROOT / args.topic / args.compare_with
        if not candidate.is_dir():
            parser.error(f"비교 폴더가 없습니다: {candidate}")
        previous_dir = candidate

    if previous_dir is not None:
        previous = load_videos(previous_dir)

    now = datetime.now(KST)
    korean: list[dict[str, Any]] = []
    unsure: list[dict[str, Any]] = []

    for video in current.values():
        verdict = classify(video, now, args.days)
        if verdict == "korean":
            korean.append(video)
        elif verdict == "unsure":
            unsure.append(video)

    korean.sort(key=lambda v: v["view_count"], reverse=True)
    picked = limit_per_channel(korean, args.per_channel)[: args.top]
    unsure.sort(key=lambda v: v["view_count"], reverse=True)

    report = format_report(
        topic=args.topic,
        current_dir=current_dir,
        previous_dir=previous_dir,
        picked=picked,
        unsure=unsure[:3],
        previous=previous,
        days=args.days,
    )
    print(report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1)
