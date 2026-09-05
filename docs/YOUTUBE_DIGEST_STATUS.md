# YouTube Digest 프로젝트 — 재시작 요약본

**갱신일 2026-09-06** · 기준 커밋 `7532f1f` · 브랜치 `main`

> API 키·토큰·비밀번호는 이 문서에 포함하지 않는다.

---

## 현재 위치 — 가장 중요한 한 문장

- YouTube Data API v3로 "AI 에이전트" 주제의 한국어 영상을 수집하고, 최근 7일 이내 영상을 조회수 순으로 5개 보고한다.
- 이전 수집분과 비교해 **조회수 변화와 순위 변동**을 계산한다.
- 매일 아침 8시 cron이 **수집 → Telegram 보고 → HTML 생성 → GitHub push → Vercel 배포**를 전부 자동으로 한다.
- **LLM을 거치지 않는 구조**라 Gemini가 429/503이어도 정상 작동한다.
- 공개 주소: `https://youtube-digest-smoky.vercel.app`
- 다음 목표는 이 구조를 KRA 프로젝트에 이식해 경마 유튜브 보고를 만드는 것이다.

---

## 1. 5분 재시작 절차

```bash
cd ~/projects/youtube-digest
source .venv/bin/activate
git log --oneline -6
git status --short
pytest -q
hermes gateway status
hermes cron status
```

### 정상 기준

| 확인 항목 | 정상 예시 | 문제 시 행동 |
| --- | --- | --- |
| 작업 폴더 | `~/projects/youtube-digest` | `cd`로 이동 |
| 가상환경 | 프롬프트 앞에 `(.venv)` | `source .venv/bin/activate` |
| 최신 커밋 | `7532f1f` 이후 | 자동 갱신 커밋이 쌓인다 |
| 원격 동기화 | `origin/main`이 같은 커밋 | `git push` |
| 테스트 | `15 passed` | failed 줄 확인 후 수정 |
| Gateway | `Active: active (running)` | `hermes gateway start` |
| Cron | `Next run: <내일 08:00>` | 위와 동일 |

### 수동 실행

전체 파이프라인을 한 번에 돌린다. API 201유닛을 쓴다.

```bash
bash ~/.hermes/scripts/youtube_daily.sh
```

마지막 줄에 `[웹페이지] 갱신 완료`가 나오면 전부 성공이다.

### 마지막 cron 보고 확인

```bash
cat $(ls -t ~/.hermes/cron/output/8b92e4108dcf/*.md | head -1)
```

### Gateway 관리

systemd 사용자 서비스로 등록되어 있다. `hermes gateway run`은 쓰지 않는다.

```bash
hermes gateway start      # 시작
hermes gateway restart    # 메모리가 쌓이면 재시작
hermes gateway status
journalctl --user -u hermes-gateway -f
```

**WSL을 껐다 켜면 죽을 수 있다.** 노트북 뚜껑만 닫는 정도로는 살아남는 것을 확인했다(25시간 연속 동작).

메모리는 하루에 100MB에서 1GB까지 늘었다. 며칠에 한 번 `restart` 하면 초기화된다.

---

## 2. 전체 구조

```
[매일 08:00 cron]  또는  [수동 실행]
              ↓
   ~/.hermes/scripts/youtube_daily.sh
              ↓
   ┌──────────┴──────────┐
   ↓                     ↓
youtube_collect_once.py   (원본 저장 + SHA-256)
   ↓
youtube_digest.py  → 텍스트 보고 → Telegram + ~/.hermes/cron/output/
   ↓
youtube_report.py  → HTML 생성 → docs/
   ↓
git commit & push  → GitHub
   ↓
Vercel 자동 배포   → https://youtube-digest-smoky.vercel.app
```

**LLM이 이 경로에 없다.** Gemini 장애와 무관하게 작동한다.

### 구성요소

| 구성요소 | 역할 | 위치 |
| --- | --- | --- |
| `youtube_collect_once.py` | API 호출, 원본 저장, manifest, SHA-256 | `scripts/` |
| `youtube_digest.py` | 텍스트 보고 (Telegram용) | `scripts/` |
| `youtube_report.py` | HTML 보고서 (웹용) | `scripts/` |
| `youtube_daily.sh` | 4단계를 순서대로 실행 | `~/.hermes/scripts/` |
| cron 작업 `8b92e4108dcf` | 매일 8시 셸 스크립트 실행 | `~/.hermes/cron/jobs.json` |
| gateway | cron 스케줄러 + Telegram | systemd 사용자 서비스 |
| `youtube` 프로필 | 이 프로젝트 전용 Hermes 프로필 | `~/.hermes/profiles/youtube/` |
| GitHub 저장소 | 코드 백업 + 배포 원본 | `HasungKoo/youtube-digest` |
| Vercel 프로젝트 | 정적 사이트 호스팅 | Root Directory `docs` |

**텍스트 보고와 HTML 보고를 다른 스크립트로 분리했다.** cron이 매일 쓰는 `youtube_digest.py`를 건드리다 깨지면 아침 보고가 안 오기 때문이다.

---

## 3. 환경과 설정

| 항목 | 값 |
| --- | --- |
| 프로젝트 | `/home/geoheim/projects/youtube-digest` |
| Python | `.venv` (requests, python-dotenv, pytest) |
| API | YouTube Data API v3 (`youtube.googleapis.com`) |
| 키 위치 | 프로젝트 `.env`의 `YOUTUBE_API_KEY` |
| GitHub 사용자 | `HasungKoo` |
| GitHub 인증 | Personal Access Token (classic), `repo` 권한 |
| 토큰 저장 | `git config --global credential.helper store` |
| Vercel 팀 | `hasungkoo's projects` (Hobby, 무료) |
| 공개 주소 | `https://youtube-digest-smoky.vercel.app` |
| cron 작업 ID | `8b92e4108dcf` |

### 할당량

일일 10,000 유닛. search 100, videos 1. **1회 수집 201유닛.**

`youtube_digest.py`와 `youtube_report.py`는 저장된 원본만 읽으므로 할당량을 쓰지 않는다.

### 보안

- `.gitignore`가 `.env`, `.venv/`, `data/raw/`, `docs/*.pdf`를 제외한다.
- push 전에 항상 확인한다.

```bash
git ls-files | grep -i env    # 아무것도 안 나와야 정상
git ls-files                   # 올라갈 파일 전체 목록
```

- manifest에 `api_key_recorded: false`로 기록하며 키 문자열이 들어가지 않는다.
- 저장소는 Public이지만 키가 없으므로 안전하다.

---

## 4. API 키 발급에서 겪은 것

**Gemini 키를 재사용하면 안 된다.** 기존 `Generative Language API Key`는 API 제한이 Gemini로 걸려 있어 YouTube 요청이 차단된다.

```
HTTP 403 API_KEY_SERVICE_BLOCKED
```

별도 키를 만들고 제한을 YouTube Data API v3로 건다.

1. Google Cloud Console → API 및 서비스 → 라이브러리
2. `YouTube Data API v3` 검색 (Analytics나 Reporting이 아니다. 서비스명 `youtube.googleapis.com`)
3. 사용 설정
4. 사용자 인증 정보 → + 만들기 → API 키
5. API 제한사항 → 키 제한 → YouTube Data API v3만 체크
6. 애플리케이션 제한사항 → 없음 (WSL은 IP가 고정이 아니다)

**`.env`를 고친 뒤 `source .env`를 다시 해야 한다.** 셸 변수는 파일을 고쳐도 자동 갱신되지 않는다.

---

## 5. 검색어 선정 과정

실제로 테스트해서 정했다.

| 검색어 | 결과 | 판정 |
| --- | --- | --- |
| `AI 에이전트` + 조회수순 | 대형 채널의 경제·투자 잡담 | 실패 |
| `"AI 에이전트" 만들기` + 최신순 | 5개 중 4개가 관련 한국어 영상 | **채택** |
| `AI 에이전트 튜토리얼` | 5개 전부 영어 | 탈락 |
| `AI 자동화 워크플로우` | 5개 전부 영어, 한 채널이 3개 도배 | 탈락 |
| `AI 에이전트 구축 실습` | 5개 중 4개 한국어 | **채택** |

### 여기서 배운 것

**외래어만 있는 검색어는 영어권 결과를 부른다.** "튜토리얼", "워크플로우"는 영어 단어와 사실상 같다. "만들기", "구축", "실습" 같은 고유어가 있어야 한국어 결과가 걸린다.

**`relevanceLanguage=ko`만으로는 부족하다.** 코드 쪽 한글 필터가 반드시 필요하다.

**`order=viewCount`는 오래된 인기 영상만 올린다.** API에서는 최신순으로 넓게 받고, 정렬은 코드가 한다.

**같은 채널이 결과를 도배한다.** 채널당 개수 제한이 필요하다.

---

## 6. 수집기 — `youtube_collect_once.py`

```bash
.venv/bin/python scripts/youtube_collect_once.py \
  --query '"AI 에이전트" 만들기' \
  --query 'AI 에이전트 구축 실습' \
  --topic ai-agent \
  --max-results 25
```

### 동작

1. 검색어마다 `search`로 최신순 목록 (검색어당 100유닛)
2. `videoId` 중복 제거
3. `videos`로 상세 조회 (1유닛, 최대 50개)
4. 원본 JSON을 타임스탬프 폴더에 저장, SHA-256 기록
5. manifest.json에 요청 조건·건수·해시·할당량 기록

### 저장 구조

```
data/raw/youtube/ai-agent/20260906T001148406811+0900/
├── search_01.json + .sha256
├── search_02.json + .sha256
├── videos.json + .sha256
└── manifest.json
```

**수집할 때마다 폴더가 쌓인다.** 조회수 변화 계산에 이전 수집분이 필요하기 때문이다.

### API 응답에서 알게 된 것

| 필드 | 어디서 | 비고 |
| --- | --- | --- |
| `videoId` | search | |
| `title`, `description` | **videos** | search는 잘린 설명과 `&quot;` 이스케이프를 준다 |
| `publishedAt` | videos | **UTC(`Z`)다. KST는 +9시간** |
| `defaultAudioLanguage` | videos | 설정 안 한 채널도 많다 |
| `viewCount` | videos | search에는 없다 |

---

## 7. 텍스트 보고 — `youtube_digest.py`

```bash
.venv/bin/python scripts/youtube_digest.py --topic ai-agent
```

새 API 호출을 하지 않는다.

| 옵션 | 기본값 | 의미 |
| --- | --- | --- |
| `--days` | 7 | 며칠 이내 영상 |
| `--top` | 5 | 보고 개수 |
| `--per-channel` | 2 | 채널당 최대 |
| `--compare-with` | previous | `previous`, `none`, 폴더명 |

### 처리 순서

```
저장된 videos.json 읽기
  → 최근 N일 필터
  → 한국어 판정 (언어 태그 ko / 한글비율 30% 이상 → korean,
                 10~30% → unsure 별도 표시, 그 외 skip)
  → 조회수 정렬
  → 채널당 N개 제한
  → 상위 N개
  → 직전 수집과 조회수 비교
```

---

## 8. HTML 보고 — `youtube_report.py`

```bash
.venv/bin/python scripts/youtube_report.py --topic ai-agent
.venv/bin/python scripts/youtube_report.py --topic ai-agent --date 2026-09-05 --out docs/index-2026-09-05.html
.venv/bin/python scripts/youtube_report.py --topic ai-agent --json
```

### 설계 원칙

**계산과 출력을 분리했다.** 계산 함수는 파이썬 자료구조를 반환하므로, 나중에 JSON API가 필요하면 그대로 재사용할 수 있다. `--json` 옵션이 그 증거다.

### 날짜별 대표 수집

`daily_runs()`가 **그날 첫 수집**을 대표로 삼는다. cron이 매일 08:00에 실행되므로 수동 실행을 몇 번 하든 기준 시각이 흔들리지 않는다.

### 화면 구성

- 날짜 선택 드롭다운 (`index-YYYY-MM-DD.html`로 이동)
- 순위 변동 화살표 (`▲2` 상승, `▼1` 하락, `–` 유지, 신규는 배지)
- 제목·채널·게시일 (제목 클릭 시 YouTube로)
- 스파크라인 (최근 7회 수집의 조회수 추이, 증가는 초록 정체는 회색)
- 조회수와 변화량
- 하단 이탈 목록 (`N위였음`)
- 다크모드 자동 대응

### 주요 함수

| 함수 | 하는 일 |
| --- | --- |
| `daily_runs(topic)` | 날짜별 대표 수집 폴더 |
| `build_ranking(run_dir, ...)` | 그날의 순위 목록 |
| `compare(current, previous)` | 순위 변동, 신규, 이탈 |
| `view_history(topic, video_id)` | 조회수 이력 (스파크라인용) |
| `build_report(...)` | 위를 합쳐 딕셔너리로 |
| `render_html(report)` | HTML 문자열 |
| `sparkline(values)` | SVG 선그래프 |

---

## 9. 자동화 — `youtube_daily.sh`

`~/.hermes/scripts/youtube_daily.sh`가 4단계를 순서대로 실행한다.

```
1. 수집          youtube_collect_once.py
2. 텍스트 보고    youtube_digest.py → 표준출력 → Telegram
3. HTML 생성     youtube_report.py (모든 날짜 + index.html)
4. git push      → Vercel 자동 배포
```

### 설계 원칙

**`--script`는 `~/.hermes/scripts/` 아래 파일만 받는다.** 프로젝트 폴더가 아니므로 스크립트 안에서 절대 경로로 `cd` 한다.

**실패해도 `exit 0`으로 끝내고 오류를 표준출력에 남긴다.** `--no-agent` 모드에서 표준출력이 비면 아무것도 전달되지 않아, "실패한 건지 잊은 건지" 알 수 없게 되기 때문이다.

**단계별로 실패를 격리했다.**

- 수집 실패 → 마지막 저장분으로 보고 시도
- 텍스트 보고 실패 → 여기서 중단 (가장 중요한 산출물)
- HTML 실패 → 텍스트 보고는 이미 나갔으므로 경고만
- push 실패 → 인증 문제로 안내

마지막 줄에 웹페이지 상태가 나온다.

```
[웹페이지] 갱신 완료 · https://youtube-digest-smoky.vercel.app
[웹페이지] 변경 없음 · ...
[웹페이지] push 실패. git 인증을 확인하세요.
```

### cron 등록

```bash
hermes cron add "0 8 * * *" \
  --name "youtube-digest-daily" \
  --script youtube_daily.sh \
  --no-agent \
  --deliver telegram
```

`--no-agent`가 핵심이다. LLM을 건너뛰고 스크립트 표준출력을 그대로 전달한다.

### schedule 표기

```
분  시  일  월  요일
0   8   *   *   *     →  매일 8시
*/30 *  *   *   *     →  30분마다
```

### 관리 명령

```bash
hermes cron list                  # 목록 + 마지막 실행 결과
hermes cron status                # 스케줄러 동작 여부
hermes cron run 8b92e4108dcf      # 즉시 실행
hermes cron runs 8b92e4108dcf     # 실행 이력
hermes cron edit 8b92e4108dcf --deliver telegram
```

### Telegram 전달

**home 채널을 설정해야 한다.** 안 하면 이렇게 실패한다.

```
⚠ Delivery failed: no delivery target resolved for deliver=telegram
```

Telegram 대화창에서 `/sethome`을 보내면 그 채팅이 수신처가 된다.

---

## 10. GitHub

### 저장소 만들기

`https://github.com/new` (UI가 바뀌어도 이 주소는 유지된다)

- Repository name: `youtube-digest`
- **README, .gitignore, license는 체크하지 않는다.** 로컬에 이미 있어 충돌한다.

### 연결과 push

```bash
git remote add origin https://github.com/HasungKoo/youtube-digest.git
git push -u origin main
```

### 인증 — Personal Access Token

**비밀번호 인증은 2021년에 막혔다.** 토큰이 필요하다.

`https://github.com/settings/tokens` → Generate new token (classic) → `repo` 권한만 체크 → Generate

`ghp_`로 시작하는 문자열이 나온다. **그 화면을 벗어나면 다시 못 본다.**

push 시 Username에 `HasungKoo`, Password에 토큰을 넣는다.

### 토큰 저장

cron이 자동 push하려면 인증이 저장돼 있어야 한다.

```bash
git config --global credential.helper store
git push        # 한 번 입력하면 저장된다
git push        # 두 번째는 아무것도 안 물어봐야 정상
```

평문으로 저장되므로 개인 노트북에서만 쓴다.

---

## 11. Vercel

### GitHub과의 관계

**GitHub은 창고, Vercel은 전시장이다.**

```
노트북에서 git push → GitHub 저장 → Vercel이 감지 → 자동 배포 → 전 세계 접속
```

노트북은 서버가 될 수 없다. 24시간 켜두고 공인 IP·방화벽·HTTPS 인증서를 다뤄야 하며, 노트북을 끄면 사이트가 죽는다. Vercel이 그걸 대신하고 무료다.

### 배포 설정

1. `https://vercel.com/signup` → Continue with GitHub
2. 플랜은 **Hobby** (개인 프로젝트, 무료)
3. 2FA 권유는 `Skip securing my account`로 건너뛸 수 있다 (나중에 켜는 것이 좋다)
4. Add New → Project → GitHub App **Install** (저장소 접근 권한)
5. `youtube-digest` → Import
6. **Root Directory를 `docs`로 바꾼다** ← 가장 중요
7. Application Preset: `Other`, Build/Output 설정은 비움
8. Deploy

**Root Directory가 핵심이다.** 기본값 `./`는 저장소 최상위인데 거기엔 `index.html`이 없다. `docs` 폴더 안에 있다.

**Environment Variables는 건드리지 않는다.** 수집은 노트북에서 하고 Vercel은 완성된 HTML만 보여준다.

### 주소 두 개

| 주소 | 성격 |
| --- | --- |
| `youtube-digest-smoky.vercel.app` | **고정 주소.** 이걸 쓴다 |
| `youtube-digest-<해시>-hasungkoo.vercel.app` | 배포마다 바뀌는 고유 주소 |

### 이후

> To update your Production Deployment, push to the `main` branch.

**`git push`만 하면 자동 갱신된다.** Vercel 웹사이트에 다시 갈 필요가 없다.

문제가 생기면 Deployments에서 이전 버전으로 되돌릴 수 있다(Instant Rollback).

---

## 12. 겪은 문제와 해결

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `HTTP 403 API_KEY_SERVICE_BLOCKED` | Gemini 키 재사용 | 별도 키 + YouTube Data API v3 제한 |
| 키를 바꿨는데 여전히 403 | `source .env`를 안 함 | 셸 변수는 자동 갱신되지 않는다 |
| 검색 결과가 전부 영어 | 검색어가 외래어뿐 | 고유어를 넣는다 |
| 같은 채널이 결과를 도배 | 자동 생성 채널 | `--per-channel` 제한 |
| 오래된 인기 영상만 나옴 | `order=viewCount` | 최신순으로 받고 코드가 정렬 |
| Hermes가 다른 프로젝트에서 일함 | 프로필의 `terminal.cwd` 고정 | 프로젝트별 프로필 생성 |
| 스킬이 로드되지 않음 | `trusted_project_dirs`에 없음 | 프로필 config에 경로 추가 |
| `hermes skills list` 결과가 흔들림 | 캐시로 보임 | chat 배너의 스킬 목록을 믿는다 |
| `Delivery failed: no delivery target` | home 채널 미설정 | Telegram에서 `/sethome` |
| cron이 실행되지 않음 | gateway 미실행 | `hermes gateway start` |
| Gemini 503 / 429 | Google 서버 문제 / 무료 티어 소진 | cron 경로는 LLM을 안 쓰므로 영향 없음 |
| git push가 비밀번호를 거부 | 비밀번호 인증 폐지 | Personal Access Token |
| Username 자리에 명령어를 입력 | 프롬프트 오해 | `HasungKoo`만 입력 |
| 터미널에 URL을 입력 | 브라우저용 주소 | 주소창에 넣는다 |
| GitHub에서 저장소 생성 버튼을 못 찾음 | UI 변경 | `https://github.com/new` 직접 입력 |
| 터미널 붙여넣기가 잘림 | WSL 터미널 한계 | **파일로 만들어 다운로드 후 `cp`** |
| 셸이 `>`에서 멈춤 | 따옴표가 안 닫힘 | `Ctrl+C` 후 한 줄로 재입력 |
| gateway 메모리가 1GB로 증가 | 장시간 동작 | `hermes gateway restart` |

### 붙여넣기 문제

100줄 넘는 파일은 터미널 붙여넣기로 만들지 않는다. 파일을 받아서 복사하는 방식이 확실하다.

```bash
cp /mnt/c/Users/geohe/Downloads/파일명 대상경로/
```

Windows가 `(1)`을 붙이면 따옴표로 감싼다.

```bash
cp "/mnt/c/Users/geohe/Downloads/파일명 (1).md" 대상경로/파일명.md
```

붙여넣은 뒤 항상 확인한다.

```bash
wc -l 파일명
tail -3 파일명
python -m py_compile 파일명    # 파이썬이면
```

---

## 13. 테스트

```bash
pytest -q      # 15 passed
```

`tests/test_youtube_digest.py`가 순수 함수를 검증한다. API를 호출하지 않는다.

| 검증 대상 | 개수 |
| --- | --- |
| `korean_ratio` | 5 |
| `classify` | 6 |
| `limit_per_channel` | 2 |
| `published_kst` | 2 |

### 테스트를 신뢰하는 방법

**통과만으로는 부족하다. 일부러 깨뜨려 실패를 확인한다.**

```bash
sed -i 's/korean_ratio"\] >= 0.30/korean_ratio"] >= 0.99/' scripts/youtube_digest.py
pytest -q tests/test_youtube_digest.py    # 1 failed 가 나와야 정상
git checkout -- scripts/youtube_digest.py
pytest -q                                  # 15 passed 로 복귀
```

**커밋 안 한 파일은 `git checkout`으로 되돌릴 수 없다.** 실험 전에 커밋해 안전지대를 만든다. (실제로 겪었다. 공백 수정이 날아갔다.)

`youtube_report.py`에 대한 테스트는 아직 없다. 나중에 `compare`, `daily_runs`, `sparkline`을 검증하면 좋다.

---

## 14. Git 상태

```
7532f1f  chore: 웹페이지 자동 갱신 2026-09-06
72ed72b  chore: 인증 저장 테스트
00f9014  feat: HTML 보고서 생성 및 초기 페이지
7eaa7b2  docs: 프로젝트 요약본 추가
52e4f7e  fix: 조회수 변화 표시의 불필요한 공백 제거
cf79f30  feat: youtube-digest 스킬 추가
1eb624f  test: 필터·정렬 로직 검증 테스트 추가
bb2ce71  feat: 수집 결과 필터·정렬·보고 스크립트 추가
7c6d83f  feat: YouTube 영상 수집기 추가
5b20616  chore: 프로젝트 초기 설정
```

브랜치 `main` · 원격 `origin` = `https://github.com/HasungKoo/youtube-digest.git`

**앞으로 cron이 매일 `chore: 웹페이지 자동 갱신 YYYY-MM-DD` 커밋을 쌓는다.**

### Git 밖에 있는 것

**이 문서가 유일한 재현 근거다.**

- `~/.hermes/profiles/youtube/` — 프로필 설정 (`terminal.cwd`, `trusted_project_dirs`)
- `~/.hermes/scripts/youtube_daily.sh` — 자동화 스크립트
- `~/.hermes/cron/jobs.json` — cron 작업 `8b92e4108dcf`
- `~/.config/systemd/user/hermes-gateway.service` — gateway 서비스
- `~/.git-credentials` — GitHub 토큰
- Vercel 프로젝트 설정 (Root Directory `docs`)
- 프로젝트 `.env` — API 키
- `data/raw/youtube/` — 수집 원본

---

## 15. 아직 하지 않은 것

**LLM 요약(B안)** — 현재는 API가 준 제목과 설명만 쓴다. 자막을 읽고 내용을 요약하려면 LLM이 필요하고 매일 토큰을 쓴다.

**KRA 이식** — 원래 목표. 검색어를 "경마 예상" 등으로 바꾸고 `--topic`을 바꾸면 된다.

**신규 배지 위치** — 조회수 아래에 붙는데 채널명 옆이 자연스럽다. 사소한 문제라 미뤘다.

**긴 제목의 세로 정렬** — 제목이 두 줄이면 스파크라인·조회수와 어긋나 보인다.

**`youtube_report.py` 테스트** — 순위 변동과 이탈 계산이 검증되지 않았다.

**주제 확장** — `--topic`을 다르게 주면 같은 스크립트로 여러 주제를 추적할 수 있다. cron 작업만 추가하면 된다.

---

## 16. KRA 프로젝트로 이식하는 방법

### 복사할 것

```bash
cp scripts/youtube_collect_once.py ~/projects/horse-agent-free-laptop-starter/scripts/
cp scripts/youtube_digest.py ~/projects/horse-agent-free-laptop-starter/scripts/
cp scripts/youtube_report.py ~/projects/horse-agent-free-laptop-starter/scripts/
cp tests/test_youtube_digest.py ~/projects/horse-agent-free-laptop-starter/tests/
```

### 바꿀 것

- KRA `.env`에 `YOUTUBE_API_KEY` 추가 (같은 키를 써도 된다)
- 검색어를 경마 주제로 — **반드시 테스트해서 정한다.** 고유어를 넣어야 한국어 결과가 나온다
- `--topic horse-racing`으로 저장 폴더 분리
- 새 SKILL.md (`horse-youtube-digest`)
- 새 cron 작업과 셸 스크립트

### 그대로 쓰는 것

- 한글 비율 계산, 기간 필터, 채널 제한, 조회수 비교, 순위 변동, 스파크라인
- manifest·SHA-256 검증 패턴
- `youtube_daily.sh` 구조 (경로·검색어·사이트 주소만 수정)

**검색어가 명령행 인자로 빠져 있어 코드는 거의 그대로다.** AGENTS.md에 "검색어와 기간은 하드코딩하지 않는다"고 적어둔 것이 여기서 값을 한다.

---

## 17. 다음 대화에 붙여넣을 재시작 프롬프트

```
나는 Windows 노트북에서 WSL2 Ubuntu 24.04를 사용하고 있다.
프로젝트 경로는 /home/geoheim/projects/youtube-digest 이다.

현재 완료 상태:
1. YouTube Data API v3 키를 발급받아 프로젝트 .env의 YOUTUBE_API_KEY에 저장했다.
   Gemini 키와 별개이며 제한이 YouTube Data API v3로 걸려 있다. 값은 출력하지 않는다.
2. scripts/youtube_collect_once.py — 검색어별 최신순 25개 + videos 상세 조회,
   원본 JSON·manifest·SHA-256 저장. 1회 201유닛, 일일 한도 10,000.
3. scripts/youtube_digest.py — 저장된 원본만 읽어 최근 7일 + 한국어 필터,
   채널당 2개 제한, 조회수 정렬, 상위 5개, 직전 수집 대비 조회수 변화.
4. scripts/youtube_report.py — 같은 데이터로 HTML 생성. 날짜별 대표 수집(그날 첫 수집)
   기준으로 순위 변동 화살표, 스파크라인, 이탈 목록, 날짜 선택 드롭다운을 만든다.
   --json 옵션으로 계산 결과만 뽑을 수도 있다.
5. 검색어는 '"AI 에이전트" 만들기' 와 'AI 에이전트 구축 실습' 두 개다.
   외래어만 있는 검색어(튜토리얼, 워크플로우)는 영어 결과만 나와서 탈락시켰다.
6. pytest 15 passed. tests/test_youtube_digest.py가 순수 함수를 검증한다.
   youtube_report.py에 대한 테스트는 아직 없다.
7. 브랜치 main, 최신 커밋 7532f1f 이후(cron이 매일 자동 커밋을 쌓는다).
   원격은 https://github.com/HasungKoo/youtube-digest.git
8. .hermes/skills/youtube-digest/SKILL.md 스킬이 있다.
9. youtube 프로필을 만들어 terminal.cwd와 trusted_project_dirs를
   youtube-digest로 지정했다. 유튜브 대화는 'youtube chat'으로 한다.
10. ~/.hermes/scripts/youtube_daily.sh 를 cron이 매일 8시에 실행한다.
    작업 ID 8b92e4108dcf, --no-agent 모드라 LLM을 거치지 않는다.
    수집 → Telegram 보고 → HTML 생성 → git push → Vercel 자동 배포까지 한다.
11. gateway는 systemd 사용자 서비스다. hermes gateway start 로 켠다.
12. 공개 주소는 https://youtube-digest-smoky.vercel.app 이다.
    Vercel의 Root Directory는 docs로 설정되어 있다.
13. GitHub 인증은 Personal Access Token이며
    git config --global credential.helper store 로 저장되어 있다.

주의사항:
- 100줄 넘는 파일은 터미널 붙여넣기로 만들지 않는다. 잘린다.
  파일로 받아서 cp 하는 방식을 쓴다.
- .env를 고친 뒤에는 source .env 를 다시 해야 한다.
- Gemini 503/429는 Google 쪽 문제다. cron 경로는 LLM을 안 쓰므로 영향받지 않는다.
- WSL을 껐다 켜면 gateway가 죽을 수 있다.
- git push 전에 git ls-files | grep -i env 로 키가 안 올라가는지 확인한다.

재개할 때 먼저 실행할 명령:
cd ~/projects/youtube-digest
source .venv/bin/activate
git log --oneline -6
git status --short
pytest -q
hermes gateway status
hermes cron status

다음 작업 후보:
- 이 구조를 KRA 프로젝트(horse-agent-free-laptop-starter)에 이식해
  경마 유튜브 보고를 만든다. 검색어는 테스트해서 정한다.
- youtube_report.py에 대한 테스트 추가.
- 필요하면 LLM 요약(B안)으로 확장.

나에게 명령을 한꺼번에 많이 주지 말고, 한 단계씩 실행 결과를 확인하면서 코치해 줘.
API 키·토큰·비밀번호는 출력하거나 요구하지 마.
```

---

## 18. 용어 정리

| 용어 | 쉽게 말하면 | 이 프로젝트의 예 |
| --- | --- | --- |
| cron | 정해진 시각에 명령을 자동 실행 | 매일 8시 |
| crontab 표기 | `분 시 일 월 요일` | `0 8 * * *` |
| `--no-agent` | LLM을 건너뛰고 스크립트 출력만 전달 | 503과 무관하게 작동 |
| home 채널 | cron 결과를 배달할 Telegram 채팅 | `/sethome` |
| systemd 서비스 | 백그라운드에서 도는 프로그램 | gateway |
| linger | 로그아웃해도 서비스 유지 | gateway install 시 자동 |
| wrapper | 긴 명령의 줄임 스크립트 | `youtube` = `hermes --profile youtube` |
| `terminal.cwd` | 그 프로필이 일하는 폴더 | 프로필마다 다르다 |
| manifest | 수집한 것의 목록과 증명서 | 건수, 해시, 할당량 |
| 할당량(유닛) | API 사용량 계량 단위 | search 100, videos 1 |
| `.gitignore` | git이 무시할 파일 목록 | `.env`, `.venv/`, `data/raw/` |
| remote / origin | 원격 저장소의 별명 | GitHub 주소 |
| Personal Access Token | 비밀번호 대신 쓰는 인증 문자열 | `ghp_`로 시작 |
| deploy | 만든 것을 서비스에 올림 | Vercel 배포 |
| Root Directory | 배포할 폴더 | `docs` |
| 스파크라인 | 축 없는 작은 추이 선그래프 | 조회수 7회 이력 |
| 정적 사이트 | 서버 계산 없이 파일만 보여주는 것 | 우리 HTML |

---

## 19. 문서 갱신 원칙

- 중요 단계가 완료될 때마다 "현재 위치"와 "다음 작업"만 갱신한다.
- API 키·토큰·개인식별정보는 복사하지 않는다.
- Git 커밋 해시, 브랜치, pytest 결과, cron 작업 ID, 공개 주소를 기록한다.
- **프로필·cron·gateway·Vercel 설정은 Git 밖에 있으므로 이 문서가 유일한 재현 근거다.**
- 검색어를 바꾸면 5장에 그 이유와 테스트 결과를 남긴다.
- 마크다운을 원본으로 Git에 두고 PDF는 필요할 때 생성한다.
- 이 문서는 `docs/YOUTUBE_DIGEST_STATUS.md`에 두고 갱신 후 커밋한다.

---

*— 요약 끝 —*

*갱신 2026-09-06 · 기준 커밋 `7532f1f` · API 키·토큰은 문서에 포함하지 않음*
