"""저장된 YouTube 수집 원본으로 HTML 보고서를 만든다.

새 API 호출을 하지 않는다. data/raw 아래 저장된 videos.json만 읽는다.
계산과 출력을 분리해 두었다. 계산 함수는 파이썬 자료구조를 반환하므로
나중에 JSON API가 필요하면 그대로 재사용할 수 있다.
"""

from __future__ import annotations

import argparse
import html
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


def published_kst(iso_utc: str) -> datetime | None:
    """UTC ISO 문자열을 KST datetime으로 바꾼다."""
    if not iso_utc:
        return None
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(KST)


def run_date(run_dir: Path) -> str:
    """수집 폴더 이름에서 날짜(YYYY-MM-DD)를 뽑는다."""
    name = run_dir.name
    return f"{name[0:4]}-{name[4:6]}-{name[6:8]}"


def run_time(run_dir: Path) -> str:
    """수집 폴더 이름에서 시각(HH:MM)을 뽑는다."""
    name = run_dir.name
    return f"{name[9:11]}:{name[11:13]}"


def daily_runs(topic: str) -> dict[str, Path]:
    """날짜별 대표 수집 폴더를 반환한다. 그날 첫 수집을 대표로 삼는다.

    cron이 매일 08:00에 실행되므로 수동 실행을 몇 번 하든
    기준 시각이 흔들리지 않는다.
    """
    topic_dir = RAW_ROOT / topic
    if not topic_dir.is_dir():
        raise FileNotFoundError(f"수집 폴더가 없습니다: {topic_dir}")

    chosen: dict[str, Path] = {}
    for path in sorted(p for p in topic_dir.iterdir() if p.is_dir()):
        date = run_date(path)
        if date not in chosen:
            chosen[date] = path

    if not chosen:
        raise FileNotFoundError(f"수집 결과가 없습니다: {topic_dir}")
    return chosen


def all_runs(topic: str) -> list[Path]:
    """모든 수집 폴더를 시간순으로 반환한다."""
    topic_dir = RAW_ROOT / topic
    return sorted(p for p in topic_dir.iterdir() if p.is_dir())


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
            "korean_ratio": korean_ratio(f"{title} {description[:500]}"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }

    return result


def classify(video: dict[str, Any], asof: datetime, days: int) -> str:
    """영상을 korean / unsure / skip 으로 분류한다."""
    published = published_kst(video["published_at"])
    if published is None or published < asof - timedelta(days=days):
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


def build_ranking(
    run_dir: Path, *, days: int, top: int, per_channel: int
) -> list[dict[str, Any]]:
    """한 수집 폴더에서 순위 목록을 만든다."""
    videos = load_videos(run_dir)

    asof = datetime.strptime(run_dir.name[:15], "%Y%m%dT%H%M%S").replace(tzinfo=KST)

    korean = [v for v in videos.values() if classify(v, asof, days) == "korean"]
    korean.sort(key=lambda v: v["view_count"], reverse=True)
    return limit_per_channel(korean, per_channel)[:top]


def view_history(topic: str, video_id: str, limit: int = 7) -> list[int]:
    """최근 수집들에서 이 영상의 조회수를 시간순으로 모은다."""
    history: list[int] = []
    for run_dir in all_runs(topic)[-limit:]:
        try:
            videos = load_videos(run_dir)
        except (FileNotFoundError, ValueError):
            continue
        video = videos.get(video_id)
        if video:
            history.append(video["view_count"])
    return history


def compare(
    current: list[dict[str, Any]], previous: list[dict[str, Any]]
) -> dict[str, Any]:
    """오늘 순위와 이전 순위를 비교해 변동과 이탈을 계산한다."""
    prev_rank = {v["video_id"]: i + 1 for i, v in enumerate(previous)}
    prev_views = {v["video_id"]: v["view_count"] for v in previous}
    current_ids = {v["video_id"] for v in current}

    rows = []
    for index, video in enumerate(current, start=1):
        vid = video["video_id"]
        row = dict(video)
        row["rank"] = index

        if vid in prev_rank:
            row["rank_change"] = prev_rank[vid] - index
            row["is_new"] = False
        else:
            row["rank_change"] = None
            row["is_new"] = True

        row["view_change"] = (
            video["view_count"] - prev_views[vid] if vid in prev_views else None
        )
        rows.append(row)

    dropped = []
    for index, video in enumerate(previous, start=1):
        if video["video_id"] not in current_ids:
            dropped.append({
                "title": video["title"],
                "channel": video["channel"],
                "previous_rank": index,
            })

    return {"rows": rows, "dropped": dropped}


def build_report(
    topic: str, *, date: str | None, days: int, top: int, per_channel: int
) -> dict[str, Any]:
    """보고서에 필요한 모든 데이터를 딕셔너리로 만든다."""
    runs = daily_runs(topic)
    dates = sorted(runs.keys())

    target = date or dates[-1]
    if target not in runs:
        raise ValueError(f"해당 날짜의 수집이 없습니다: {target}")

    current_dir = runs[target]
    index = dates.index(target)
    previous_dir = runs[dates[index - 1]] if index > 0 else None

    current = build_ranking(current_dir, days=days, top=top, per_channel=per_channel)
    previous = (
        build_ranking(previous_dir, days=days, top=top, per_channel=per_channel)
        if previous_dir
        else []
    )

    result = compare(current, previous)

    for row in result["rows"]:
        row["history"] = view_history(topic, row["video_id"])

    return {
        "topic": topic,
        "date": target,
        "time": run_time(current_dir),
        "previous_date": dates[index - 1] if index > 0 else None,
        "available_dates": dates,
        "days": days,
        "rows": result["rows"],
        "dropped": result["dropped"],
    }


def sparkline(values: list[int], width: int = 64, height: int = 26) -> str:
    """조회수 이력을 작은 SVG 선그래프로 만든다."""
    if len(values) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'

    low, high = min(values), max(values)
    span = high - low if high > low else 1
    step = (width - 4) / (len(values) - 1)

    points = []
    for i, value in enumerate(values):
        x = 2 + i * step
        y = height - 2 - ((value - low) / span) * (height - 4)
        points.append(f"{x:.1f},{y:.1f}")

    growth = (values[-1] - values[0]) / max(values[0], 1)
    color = "#1D9E75" if growth > 0.01 else "#888780"
    last_x, last_y = points[-1].split(",")

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2.5" fill="{color}"/>'
        f"</svg>"
    )


def rank_badge(change: int | None, is_new: bool) -> str:
    """순위 변동 표시를 만든다."""
    if is_new:
        return ""
    if change is None or change == 0:
        return '<span class="rank-same">–</span>'
    if change > 0:
        return f'<span class="rank-up">&#9650;{change}</span>'
    return f'<span class="rank-down">&#9660;{abs(change)}</span>'


def render_html(report: dict[str, Any]) -> str:
    """보고서 데이터를 HTML 문자열로 만든다."""
    esc = html.escape

    options = "".join(
        f'<option value="{d}"{" selected" if d == report["date"] else ""}>{d}</option>'
        for d in reversed(report["available_dates"])
    )

    rows_html = []
    for row in report["rows"]:
        published = published_kst(row["published_at"])
        date_text = published.strftime("%m-%d") if published else "?"

        if row["is_new"]:
            change_html = '<span class="new">신규</span>'
        elif row["view_change"] is None:
            change_html = ""
        elif row["view_change"] == 0:
            change_html = '<span class="flat">변화 없음</span>'
        else:
            change_html = f'<span class="up">+{row["view_change"]:,}</span>'

        rows_html.append(f"""
      <div class="row">
        <div class="rank">{row["rank"]}{rank_badge(row["rank_change"], row["is_new"])}</div>
        <div class="main">
          <a href="{esc(row["url"])}" target="_blank" rel="noopener">{esc(row["title"])}</a>
          <div class="meta">{esc(row["channel"])} · {date_text}</div>
        </div>
        <div class="spark">{sparkline(row["history"])}</div>
        <div class="views">
          <div class="count">{row["view_count"]:,}</div>
          <div class="change">{change_html}</div>
        </div>
      </div>""")

    dropped_html = ""
    if report["dropped"]:
        items = "".join(
            f'<div class="drop">{esc(d["title"])}'
            f'<span class="why">· {d["previous_rank"]}위였음</span></div>'
            for d in report["dropped"]
        )
        dropped_html = f"""
      <div class="dropped">
        <div class="drop-label">순위에서 빠짐</div>
        {items}
      </div>"""

    compare_text = (
        f'{report["previous_date"]} 대비'
        if report["previous_date"]
        else "비교 대상 없음"
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(report["topic"])} 다이제스트</title>
<style>
  :root {{
    --text: #1a1a1a; --muted: #6b6b68; --line: #e5e3dd;
    --card: #ffffff; --bg: #faf9f7;
    --up: #0f6e56; --down: #a32d2d; --accent: #185fa5;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --text: #e8e6e0; --muted: #9c9a92; --line: #34332f;
      --card: #232320; --bg: #1a1a18;
      --up: #5dcaa5; --down: #f09595; --accent: #85b7eb;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 2rem 1rem; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 720px; margin: 0 auto; }}
  .controls {{ display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }}
  select {{
    font: inherit; font-size: 14px; padding: 6px 10px; border-radius: 8px;
    border: 1px solid var(--line); background: var(--card); color: var(--text);
  }}
  .card {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 12px; padding: 1rem 1.25rem;
  }}
  .head {{
    display: flex; justify-content: space-between; align-items: baseline;
    border-bottom: 1px solid var(--line); padding-bottom: 12px;
  }}
  .head strong {{ font-size: 16px; font-weight: 500; }}
  .head span {{ font-size: 12px; color: var(--muted); }}
  .row {{
    display: flex; gap: 10px; align-items: center;
    padding: 14px 0; border-bottom: 1px solid var(--line);
  }}
  .row:last-of-type {{ border-bottom: none; }}
  .rank {{ min-width: 36px; align-self: flex-start; padding-top: 2px; font-size: 13px; color: var(--muted); }}
  .rank-up {{ color: var(--up); font-size: 11px; margin-left: 3px; }}
  .rank-down {{ color: var(--down); font-size: 11px; margin-left: 3px; }}
  .rank-same {{ color: var(--muted); font-size: 11px; margin-left: 3px; }}
  .main {{ flex: 1; min-width: 0; }}
  .main a {{ color: var(--text); text-decoration: none; font-size: 14px; line-height: 1.45; }}
  .main a:hover {{ color: var(--accent); text-decoration: underline; }}
  .meta {{ font-size: 12px; color: var(--muted); margin-top: 3px; }}
  .spark {{ flex-shrink: 0; line-height: 0; }}
  .views {{ text-align: right; flex-shrink: 0; min-width: 74px; }}
  .count {{ font-size: 16px; font-weight: 500; }}
  .change {{ font-size: 12px; }}
  .up {{ color: var(--up); }}
  .flat {{ color: var(--muted); }}
  .new {{
    color: var(--accent); font-size: 11px;
    border: 1px solid var(--line); border-radius: 6px; padding: 1px 6px;
  }}
  .dropped {{ border-top: 1px solid var(--line); padding-top: 12px; margin-top: 4px; }}
  .drop-label {{ font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
  .drop {{ font-size: 13px; color: var(--muted); line-height: 1.6; }}
  .why {{ margin-left: 6px; opacity: 0.7; }}
  footer {{ font-size: 12px; color: var(--muted); margin-top: 1rem; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">

  <div class="controls">
    <select id="date-picker" onchange="location.href='index-' + this.value + '.html'">
      {options}
    </select>
    <span style="font-size:13px;color:var(--muted)">{esc(compare_text)}</span>
  </div>

  <div class="card">
    <div class="head">
      <strong>{esc(report["topic"])} · 최근 {report["days"]}일</strong>
      <span>{report["date"]} {report["time"]} 기준</span>
    </div>
{"".join(rows_html)}
{dropped_html}
  </div>

  <footer>YouTube Data API v3 · 매일 08:00 자동 수집</footer>
</div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube 다이제스트 HTML 보고서")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD, 생략하면 최신")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--per-channel", type=int, default=2)
    parser.add_argument("--out", default="docs/index.html")
    parser.add_argument("--json", action="store_true", help="HTML 대신 JSON 출력")
    args = parser.parse_args()

    report = build_report(
        args.topic,
        date=args.date,
        days=args.days,
        top=args.top,
        per_channel=args.per_channel,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    out_path = PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(report), encoding="utf-8")

    print(f"{report['date']} 기준 {len(report['rows'])}건")
    print(f"저장: {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1)
