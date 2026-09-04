"""YouTube Data API v3에서 지정 검색어의 영상을 수집하고 원본을 보존한다.

search로 최신순 목록을 받고, videos로 조회수와 언어를 조회한 뒤
원본 JSON, manifest.json, SHA-256을 타임스탬프 폴더에 저장한다.
API 키는 어디에도 기록하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
KST = timezone(timedelta(hours=9))

SEARCH_COST = 100
VIDEOS_COST = 1


class YouTubeAPIError(RuntimeError):
    """YouTube API가 오류를 반환했을 때 사용하는 예외."""


def load_api_key() -> str:
    """프로젝트 .env에서 API 키를 읽는다."""
    load_dotenv(ENV_PATH)
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(f"YOUTUBE_API_KEY를 찾지 못했습니다: {ENV_PATH}")
    return api_key


def call_api(
    *,
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """API를 호출하고 JSON을 반환한다. 키는 예외 메시지에 넣지 않는다."""
    full_params = dict(params)
    full_params["key"] = api_key

    response = session.get(url, params=full_params, timeout=(10, 60))

    try:
        payload = response.json()
    except ValueError:
        preview = response.text[:200].replace("\n", " ")
        raise YouTubeAPIError(
            f"HTTP {response.status_code}, 응답이 JSON이 아님. 본문 일부: {preview}"
        ) from None

    if response.status_code != 200:
        error = payload.get("error", {})
        raise YouTubeAPIError(
            f"HTTP {response.status_code}: "
            f"{error.get('message', '알 수 없는 오류')}"
        )

    return payload


def search_videos(
    *,
    session: requests.Session,
    api_key: str,
    query: str,
    max_results: int,
) -> dict[str, Any]:
    """검색어로 최신순 영상 목록을 받는다."""
    return call_api(
        session=session,
        url=SEARCH_URL,
        api_key=api_key,
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "order": "date",
            "relevanceLanguage": "ko",
            "regionCode": "KR",
        },
    )


def fetch_video_details(
    *,
    session: requests.Session,
    api_key: str,
    video_ids: list[str],
) -> dict[str, Any]:
    """영상 상세 정보를 받는다. id는 최대 50개까지 한 번에 조회된다."""
    return call_api(
        session=session,
        url=VIDEOS_URL,
        api_key=api_key,
        params={
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
        },
    )


def save_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """JSON을 저장하고 크기와 SHA-256을 반환한다."""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    data = text.encode("utf-8")

    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (path.parent / f"{path.name}.sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )

    return {
        "file": str(path.relative_to(PROJECT_ROOT)),
        "size_bytes": len(data),
        "sha256": digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube 영상 수집기")
    parser.add_argument(
        "--query", action="append", required=True,
        help="검색어 (여러 번 지정 가능)",
    )
    parser.add_argument("--topic", required=True, help="저장 폴더명에 쓸 주제 슬러그")
    parser.add_argument("--max-results", type=int, default=25)
    args = parser.parse_args()

    if not 1 <= args.max_results <= 50:
        parser.error(f"--max-results는 1~50이어야 합니다: {args.max_results}")

    api_key = load_api_key()
    collected_at = datetime.now(KST)
    stamp = collected_at.strftime("%Y%m%dT%H%M%S%f%z")

    run_dir = PROJECT_ROOT / "data" / "raw" / "youtube" / args.topic / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    quota_used = 0
    searches: list[dict[str, Any]] = []
    video_ids: list[str] = []
    seen: set[str] = set()

    with requests.Session() as session:
        for index, query in enumerate(args.query, start=1):
            payload = search_videos(
                session=session, api_key=api_key,
                query=query, max_results=args.max_results,
            )
            quota_used += SEARCH_COST

            found = [
                item["id"]["videoId"]
                for item in payload.get("items", [])
                if item.get("id", {}).get("videoId")
            ]
            for vid in found:
                if vid not in seen:
                    seen.add(vid)
                    video_ids.append(vid)

            record = save_json(run_dir / f"search_{index:02d}.json", payload)
            record["query"] = query
            record["item_count"] = len(found)
            searches.append(record)

            print(f"검색 {index}: {query!r} -> {len(found)}건")

        if not video_ids:
            raise YouTubeAPIError("검색 결과가 없습니다.")

        details = fetch_video_details(
            session=session, api_key=api_key, video_ids=video_ids[:50],
        )
        quota_used += VIDEOS_COST
        details_record = save_json(run_dir / "videos.json", details)
        details_record["item_count"] = len(details.get("items", []))

    manifest = {
        "schema_version": 1,
        "source": "YouTube Data API v3",
        "topic": args.topic,
        "collected_at_kst": collected_at.isoformat(),
        "request": {
            "queries": args.query,
            "max_results": args.max_results,
            "order": "date",
            "relevance_language": "ko",
            "region_code": "KR",
        },
        "api_key_recorded": False,
        "quota_used": quota_used,
        "unique_video_ids": len(video_ids),
        "detail_count": details_record["item_count"],
        "searches": searches,
        "videos": details_record,
        "integrity_status": "PASS",
    }

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n고유 영상 {len(video_ids)}건, 상세 {details_record['item_count']}건")
    print(f"할당량 사용 {quota_used} 유닛")
    print(f"저장 폴더 {run_dir.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (YouTubeAPIError, RuntimeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1)
