# YouTube Digest 프로젝트 — 재시작 요약본

**작성일 2026-09-04** · 기준 커밋 `52e4f7e` · 브랜치 `main`

> API 키·토큰·비밀번호는 이 문서에 포함하지 않는다.

---

## 현재 위치 — 가장 중요한 한 문장

- YouTube Data API v3로 "AI 에이전트" 주제의 한국어 영상을 수집하고, 최근 7일 이내 영상을 조회수 순으로 5개 보고하는 시스템을 하루 만에 완성했다.
- 이전 수집분과 비교해 **조회수 변화**를 계산한다.
- 매일 아침 8시 cron이 자동 실행하고 결과를 **Telegram과 파일**로 남긴다.
- **LLM을 거치지 않는 구조**라 Gemini가 429/503이어도 보고는 정상 작동한다.
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
| 브랜치 | `main` | 확인 |
| 최신 커밋 | `52e4f7e` | 이후 작업이 있으면 갱신 |
| 테스트 | `15 passed` | failed 줄 확인 후 수정 |
| Gateway | `Active: active (running)` | `hermes gateway start` |
| Cron | `Gateway is running — cron jobs will fire` | 위와 동일 |

### Gateway 시작

**systemd 서비스로 등록되어 있다.** 예전처럼 `hermes gateway run`을 쓰지 않는다.

```bash
hermes gateway start
```

- 백그라운드로 돌아 터미널을 붙잡지 않는다.
- 로그는 화면이 아니라 저널에 쌓인다. `journalctl --user -u hermes-gateway -f`
- linger가 켜져 있어 로그아웃해도 유지된다.
- **WSL을 껐다 켜면(`wsl --shutdown`, 재부팅) 죽을 수 있다.** 그때 다시 `start`.

### 마지막 보고 확인

```bash
cat $(ls -t ~/.hermes/cron/output/8b92e4108dcf/*.md | head -1)
```

---

## 2. 시스템 구조

```
[사용자 수동 실행]                    [매일 08:00 cron]
        │                                    │
        └──────────┬─────────────────────────┘
                   ↓
      ~/.hermes/scripts/youtube_daily.sh
                   ↓
   ┌───────────────┴───────────────┐
   ↓                               ↓
youtube_collect_once.py      youtube_digest.py
   ↓                               ↓
[YouTube Data API v3]        [저장된 원본 읽기]
   ↓                               ↓
data/raw/youtube/            7일·한국어 필터
 + manifest + SHA-256        채널당 2개 제한
                             조회수 정렬
                             직전 수집과 비교
                                   ↓
                   ┌───────────────┴──────────────┐
                   ↓                              ↓
            Telegram (home 채널)      ~/.hermes/cron/output/
```

**LLM이 이 경로에 없다.** 그래서 Gemini 장애와 무관하게 작동한다.

### 구성요소

| 구성요소 | 역할 | 위치 |
| --- | --- | --- |
| `youtube_collect_once.py` | API 호출, 원본 저장, manifest, SHA-256 | `scripts/` |
| `youtube_digest.py` | 필터·정렬·비교·보고문 생성 | `scripts/` |
| `youtube_daily.sh` | 두 스크립트를 순서대로 실행 | `~/.hermes/scripts/` |
| cron 작업 | 매일 8시 셸 스크립트 실행 | `~/.hermes/cron/jobs.json` |
| gateway | cron 스케줄러 + Telegram 연결 | systemd 사용자 서비스 |
| `youtube` 프로필 | 이 프로젝트 전용 Hermes 프로필 | `~/.hermes/profiles/youtube/` |

---

## 3. 환경과 설정

| 항목 | 값 |
| --- | --- |
| 프로젝트 | `/home/geoheim/projects/youtube-digest` |
| Python | `.venv` (requests, python-dotenv, pytest) |
| API | YouTube Data API v3 (`youtube.googleapis.com`) |
| 키 위치 | 프로젝트 `.env`의 `YOUTUBE_API_KEY` |
| Google Cloud 프로젝트 | Gemini API와 같은 프로젝트 사용 |
| cron 작업 ID | `8b92e4108dcf` |
| Telegram home 채널 | 설정 완료 (`/sethome`) |

### 할당량

일일 10,000 유닛.

| 호출 | 비용 |
| --- | --- |
| search | 100 유닛 |
| videos | 1 유닛 |
| **1회 수집 (검색어 2개 + 상세 1회)** | **201 유닛** |

하루 40회 이상 가능하다. cron 1회 + 수동 몇 번은 여유롭다.

### 보안

- `YOUTUBE_API_KEY`는 `.env`에만 두고 `chmod 600`.
- `.gitignore`가 `.env`, `.venv/`, `data/raw/`, `docs/*.pdf`를 제외한다.
- manifest에 `api_key_recorded: false`로 기록하며 키 문자열이 들어가지 않는다.

---

## 4. API 키 발급에서 겪은 것

**Gemini 키를 재사용하면 안 된다.** 기존 `Generative Language API Key`는 API 제한이 Gemini로 걸려 있어 YouTube 요청이 차단된다.

```
HTTP 403 API_KEY_SERVICE_BLOCKED
Requests to this API youtube method ... are blocked.
```

**별도 키를 만들고 제한을 YouTube Data API v3로 건다.**

1. Google Cloud Console → API 및 서비스 → 라이브러리
2. `YouTube Data API v3` 검색 (Analytics나 Reporting이 아니다. 서비스명 `youtube.googleapis.com`)
3. 사용 설정
4. 사용자 인증 정보 → + 만들기 → API 키
5. API 제한사항 → 키 제한 → YouTube Data API v3만 체크
6. 애플리케이션 제한사항 → 없음 (WSL은 IP가 고정이 아니다)

**`.env`를 고친 뒤 `source .env`를 다시 해야 한다.** 셸 변수는 파일을 고쳐도 자동 갱신되지 않는다.

---

## 5. 검색어 선정 과정

실제로 테스트해서 정했다. 이 과정 자체가 중요한 학습이었다.

| 검색어 | 결과 | 판정 |
| --- | --- | --- |
| `AI 에이전트` + 조회수순 | 대형 채널의 경제·투자 잡담 | 실패 |
| `"AI 에이전트" 만들기` + 최신순 | 5개 중 4개가 관련 한국어 영상 | **채택** |
| `AI 에이전트 튜토리얼` | 5개 전부 영어 | 탈락 |
| `AI 자동화 워크플로우` | 5개 전부 영어, 한 채널이 3개 도배 | 탈락 |
| `AI 에이전트 구축 실습` | 5개 중 4개 한국어 | **채택** |

### 여기서 배운 것

**외래어만 있는 검색어는 영어권 결과를 부른다.** "튜토리얼", "워크플로우"는 영어 단어와 사실상 같다. "만들기", "구축", "실습" 같은 고유어가 있어야 한국어 결과가 걸린다.

**`relevanceLanguage=ko`만으로는 부족하다.** 파라미터를 줘도 영어 영상이 섞인다. 코드 쪽 한글 필터가 반드시 필요하다.

**`order=viewCount`는 오래된 인기 영상만 올린다.** 어제 올라온 영상은 조회수가 낮을 수밖에 없다. **API에서는 최신순으로 넓게 받고, 정렬은 코드가 한다.**

**같은 채널이 여러 개 차지한다.** 자동 생성 채널은 비슷한 제목으로 도배한다. 채널당 개수 제한이 필요하다.

---

## 6. 수집기 — `youtube_collect_once.py`

### 실행

```bash
.venv/bin/python scripts/youtube_collect_once.py \
  --query '"AI 에이전트" 만들기' \
  --query 'AI 에이전트 구축 실습' \
  --topic ai-agent \
  --max-results 25
```

`--query`는 반복 지정할 수 있다. `--topic`은 저장 폴더명이 된다.

### 동작

1. 검색어마다 `search`로 최신순 목록을 받는다 (검색어당 100 유닛)
2. `videoId`를 모아 중복을 제거한다
3. `videos`로 상세 정보를 한 번에 조회한다 (1 유닛, 최대 50개)
4. 원본 JSON을 타임스탬프 폴더에 저장하고 SHA-256을 남긴다
5. manifest.json에 요청 조건·건수·해시·할당량을 기록한다

### 저장 구조

```
data/raw/youtube/ai-agent/20260904T121441975762+0900/
├── search_01.json + .sha256
├── search_02.json + .sha256
├── videos.json + .sha256
└── manifest.json
```

**수집할 때마다 폴더가 쌓인다.** 조회수 변화를 계산하려면 이전 수집분이 남아 있어야 하기 때문이다.

### API 응답에서 알게 된 것

| 필드 | 어디서 | 비고 |
| --- | --- | --- |
| `videoId` | search | |
| `title`, `description` | **videos** | search는 잘린 설명과 `&quot;` 이스케이프를 준다 |
| `publishedAt` | videos | **UTC(`Z`)다. KST는 +9시간** |
| `defaultAudioLanguage` | videos | 설정 안 한 채널도 많다 |
| `viewCount`, `likeCount` | videos | search에는 없다 |

**두 단계 호출이 필요하다.** search는 조회수를 주지 않고, videos가 훨씬 싸다(1 유닛).

---

## 7. 보고기 — `youtube_digest.py`

### 실행

```bash
.venv/bin/python scripts/youtube_digest.py --topic ai-agent
```

**새 API 호출을 하지 않는다.** 저장된 원본만 읽으므로 할당량을 쓰지 않는다.

### 옵션

| 옵션 | 기본값 | 의미 |
| --- | --- | --- |
| `--days` | 7 | 며칠 이내 영상을 볼지 |
| `--top` | 5 | 몇 개를 보고할지 |
| `--per-channel` | 2 | 같은 채널에서 최대 몇 개 |
| `--compare-with` | previous | `previous`, `none`, 또는 폴더명 |

특정 시점과 비교하려면 폴더명을 직접 지정한다.

```bash
ls -1 data/raw/youtube/ai-agent/
.venv/bin/python scripts/youtube_digest.py --topic ai-agent \
  --compare-with 20260904T121441975762+0900
```

### 처리 순서

```
저장된 videos.json 읽기
  ↓
최근 N일 이내 필터
  ↓
한국어 판정
  ├─ defaultAudioLanguage 또는 defaultLanguage가 ko → korean
  ├─ 한글 비율 30% 이상 → korean
  ├─ 한글 비율 10~30% → unsure (별도 표시)
  └─ 그 외 → skip
  ↓
조회수 높은 순 정렬
  ↓
채널당 최대 N개로 제한 (정렬 순서 유지)
  ↓
상위 N개 선정
  ↓
직전 수집과 조회수 비교
```

**한국어 판정이 애매한 것(10~30%)은 버리지 않고 별도로 표시한다.** 모르는 것을 아는 척하지 않는 원칙이다.

### 출력 예시

```
[ai-agent] 최근 7일 한국어 영상 5건
수집 시점: 20260904T231934955155+0900
비교 대상: 20260904T231103810907+0900

1. 암묵지 자산화를 위한 딥트윈 에이전트의 전체 원리와 설계 프로세스
   양실장의 바이브코딩대학 · 08-31 21:00
   조회 31,748  (+11)
   https://www.youtube.com/watch?v=...
```

괄호 표시의 의미.

- `(+55)` 조회수가 55 늘었다
- `(변화 없음)` 조회수가 같다
- `(신규)` 이전 수집에는 없던 영상이다

---

## 8. 자동화 — cron

### 셸 스크립트

`~/.hermes/scripts/youtube_daily.sh`가 두 파이썬 스크립트를 순서대로 실행한다.

**`--script`는 `~/.hermes/scripts/` 아래 파일만 받는다.** 프로젝트 폴더가 아니므로 스크립트 안에서 절대 경로로 `cd` 한다.

**실패해도 `exit 0`으로 끝내고 오류를 표준출력에 남긴다.** `--no-agent` 모드에서 표준출력이 비면 아무것도 전달되지 않아, "실패한 건지 잊은 건지" 알 수 없게 되기 때문이다.

수집이 실패하면 마지막 저장분으로 보고를 시도한다.

### 등록

```bash
hermes cron add "0 8 * * *" \
  --name "youtube-digest-daily" \
  --script youtube_daily.sh \
  --no-agent \
  --deliver telegram
```

`--no-agent`가 핵심이다. **LLM을 건너뛰고 스크립트 표준출력을 그대로 전달한다.** 토큰을 쓰지 않고 Gemini 장애와 무관하다.

### schedule 표기

```
분  시  일  월  요일
0   8   *   *   *     →  매일 8시 0분
0   8   *   *   1     →  매주 월요일 8시
*/30 *  *   *   *     →  30분마다
```

`every 2h`, `30m` 같은 표기도 받는다.

### 관리 명령

```bash
hermes cron list                  # 등록된 작업 목록 + 마지막 실행 결과
hermes cron status                # 스케줄러가 도는지
hermes cron run 8b92e4108dcf      # 즉시 실행
hermes cron runs 8b92e4108dcf     # 실행 이력
hermes cron edit 8b92e4108dcf --deliver telegram
hermes cron pause / resume / remove
```

### 출력 저장 위치

```
~/.hermes/cron/output/8b92e4108dcf/2026-09-04_22-56-56.md
```

작업 ID별 폴더에 실행 시각별 파일이 쌓인다. Telegram이 실패해도 여기 남는다.

### Telegram 전달

**home 채널을 설정해야 한다.** 안 하면 이렇게 실패한다.

```
⚠ Delivery failed: no delivery target resolved for deliver=telegram
```

Telegram 대화창에서 `/sethome`을 보내면 그 채팅이 수신처가 된다.

### Gateway

**cron 스케줄러는 gateway 안에 있다.** gateway가 꺼져 있으면 작업이 실행되지 않는다.

systemd 사용자 서비스로 등록했다.

```bash
hermes gateway install --start-now --start-on-login   # 최초 1회
hermes gateway start                                  # 이후 시작
hermes gateway status
journalctl --user -u hermes-gateway -f                # 로그 보기
```

**설치 시 WSL 경고가 뜬다.**

```
⚠ WSL detected — systemd services may not survive WSL restarts.
```

노트북을 껐다 켜거나 `wsl --shutdown` 후에는 `hermes gateway start`로 다시 켜야 할 수 있다. 대안으로 tmux를 쓸 수도 있다.

---

## 9. Hermes 프로필과 작업 디렉토리

**오늘 겪은 가장 헷갈린 문제다.**

### 증상

`youtube-digest` 폴더에서 `hermes chat`을 띄웠는데 Hermes가 KRA 폴더에서 일했다.

```
현재 프로젝트 디렉토리(horse-agent-free-laptop-starter)에 존재하지 않습니다
```

스킬도 KRA 것 2개가 로드되고 `youtube-digest`는 안 보였다.

### 원인

**프로필의 `config.yaml`에 작업 디렉토리가 고정되어 있다.** 터미널이 어디 있든 상관없다.

```yaml
terminal:
  cwd: /home/geoheim/projects/horse-agent-free-laptop-starter
skills:
  trusted_project_dirs:
    - /home/geoheim/projects/horse-agent-free-laptop-starter
```

### 해결

프로젝트마다 프로필을 나눈다.

```bash
hermes profile create youtube --clone --description "..."
nano ~/.hermes/profiles/youtube/config.yaml
```

두 곳을 고친다.

```yaml
terminal:
  cwd: /home/geoheim/projects/youtube-digest
skills:
  trusted_project_dirs:
    - /home/geoheim/projects/youtube-digest
```

### 현재 프로필 구성

| 프로필 | 작업 폴더 | 역할 |
| --- | --- | --- |
| `default` | KRA | Telegram 연결, cron 실행 |
| `data-collector` | KRA | 수집 담당 |
| `data-reviewer` | KRA | 검토 담당 |
| `youtube` | youtube-digest | 유튜브 전용 |

```
유튜브 대화  →  youtube chat
KRA 대화     →  hermes chat
```

**wrapper** — `~/.local/bin/youtube`는 `hermes --profile youtube`의 줄임말이다. 프로필 생성 시 자동으로 만들어진다.

**cron은 프로필과 무관하다.** `--no-agent` 모드라 셸 스크립트가 절대 경로로 실행되기 때문이다.

---

## 10. 겪은 문제와 해결

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `HTTP 403 API_KEY_SERVICE_BLOCKED` | Gemini 키를 재사용, API 제한에 YouTube 없음 | 별도 키 생성 후 제한을 YouTube Data API v3로 |
| 키를 바꿨는데 여전히 403 | `source .env`를 안 함 | 셸 변수는 자동 갱신되지 않는다 |
| 검색 결과가 전부 영어 | 검색어가 외래어뿐 | 고유어("만들기", "실습")를 넣는다 |
| 같은 채널이 결과를 도배 | 자동 생성 채널 | `--per-channel` 제한 |
| 오래된 인기 영상만 나옴 | `order=viewCount` | 최신순으로 받고 코드가 정렬 |
| Hermes가 다른 프로젝트에서 일함 | 프로필의 `terminal.cwd` 고정 | 프로젝트별 프로필 생성 |
| 스킬이 로드되지 않음 | `trusted_project_dirs`에 없음 | 프로필 config에 경로 추가 |
| `hermes skills list` 결과가 흔들림 | 캐시로 보임 | 목록보다 **chat 배너의 스킬 목록**을 믿는다 |
| `Delivery failed: no delivery target` | home 채널 미설정 | Telegram에서 `/sethome` |
| cron이 실행되지 않음 | gateway 미실행 | `hermes gateway start` |
| Gemini HTTP 503 | Google 서버 과부하 (내 문제 아님) | 기다린다. cron 경로는 영향 없음 |
| 터미널 붙여넣기가 잘림 | WSL 터미널이 긴 텍스트를 못 받음 | **파일로 만들어 다운로드 후 `cp`** |
| 셸이 `>`에서 멈춤 | 따옴표가 안 닫힘 | `Ctrl+C` 후 한 줄로 재입력 |

### 붙여넣기 문제

이 프로젝트에서 반복해서 겪었다. 100줄 넘는 파일은 터미널 붙여넣기로 만들지 않는다.

**파일을 받아서 복사하는 방식이 확실하다.**

```bash
cp /mnt/c/Users/geohe/Downloads/파일명 대상경로/
```

Windows가 같은 이름을 피해 `(1)`을 붙이면 따옴표로 감싼다.

```bash
cp "/mnt/c/Users/geohe/Downloads/파일명 (1).md" 대상경로/파일명.md
```

붙여넣은 뒤에는 항상 확인한다.

```bash
wc -l 파일명
tail -3 파일명
python -m py_compile 파일명    # 파이썬이면
```

---

## 11. 테스트

```bash
pytest -q      # 15 passed
```

`tests/test_youtube_digest.py`가 순수 함수를 검증한다. API를 호출하지 않는다.

| 검증 대상 | 개수 |
| --- | --- |
| `korean_ratio` — 한글 비율 계산 | 5 |
| `classify` — 한국어·기간 판정 | 6 |
| `limit_per_channel` — 채널 제한과 순서 유지 | 2 |
| `published_kst` — UTC→KST 변환, 잘못된 입력 | 2 |

### 테스트를 신뢰하는 방법

**통과만으로는 부족하다. 일부러 깨뜨려 실패를 확인한다.**

```bash
sed -i 's/korean_ratio"\] >= 0.30/korean_ratio"] >= 0.99/' scripts/youtube_digest.py
pytest -q tests/test_youtube_digest.py    # 1 failed 가 나와야 정상
git checkout -- scripts/youtube_digest.py
pytest -q                                  # 15 passed 로 복귀
```

실제로 `test_classify_korean_by_ratio`가 실패했고 나머지 14개는 통과했다. 테스트가 독립적으로 작동한다는 증거다.

**커밋 안 한 파일은 `git checkout`으로 되돌릴 수 없다.** 실험 전에 커밋해 안전지대를 만든다. (이 프로젝트에서 실제로 겪었다. 커밋 전에 되돌려 수정이 날아갔다.)

---

## 12. Git 상태

```
52e4f7e  fix: 조회수 변화 표시의 불필요한 공백 제거
cf79f30  feat: youtube-digest 스킬 추가
1eb624f  test: 필터·정렬 로직 검증 테스트 추가
bb2ce71  feat: 수집 결과 필터·정렬·보고 스크립트 추가
7c6d83f  feat: YouTube 영상 수집기 추가
5b20616  chore: 프로젝트 초기 설정
```

브랜치 `main` · working tree clean

### Git 밖에 있는 것

**이 문서가 유일한 재현 근거다.**

- `~/.hermes/profiles/youtube/` — 프로필 설정
- `~/.hermes/scripts/youtube_daily.sh` — cron 셸 스크립트
- `~/.hermes/cron/jobs.json` — cron 작업 정의
- `~/.config/systemd/user/hermes-gateway.service` — gateway 서비스
- `data/raw/youtube/` — 수집 원본 (gitignore)
- 프로젝트 `.env` — API 키 (gitignore)

---

## 13. 아직 하지 않은 것

**LLM 요약(B안)** — 현재는 API가 준 제목과 설명만 쓴다. 자막을 읽고 내용을 요약하려면 LLM이 필요하고 매일 토큰을 쓴다.

**KRA 이식** — 원래 목표. 검색어를 "경마 예상", "경마 분석" 등으로 바꾸고 `--topic`을 바꾸면 된다. 검색어가 명령행 인자로 빠져 있어 코드 수정이 거의 필요 없다.

**주제 확장** — `--topic`을 다르게 주면 같은 스크립트로 여러 주제를 추적할 수 있다. cron 작업만 추가하면 된다.

**Telegram 표시 정리** — 현재 URL과 번호가 마크다운으로 잘못 묶인다. 읽는 데 지장은 없다.

**제목 키워드 재확인** — 검색어에 걸렸지만 주제가 벗어난 영상이 5개 중 1개 정도 섞인다.

---

## 14. KRA 프로젝트로 이식하는 방법

원래 목표였다. 실제로 옮길 때 할 일.

### 복사할 것

```bash
cp scripts/youtube_collect_once.py ~/projects/horse-agent-free-laptop-starter/scripts/
cp scripts/youtube_digest.py ~/projects/horse-agent-free-laptop-starter/scripts/
cp tests/test_youtube_digest.py ~/projects/horse-agent-free-laptop-starter/tests/
```

### 바꿀 것

- KRA 프로젝트 `.env`에 `YOUTUBE_API_KEY` 추가 (같은 키를 써도 된다)
- 검색어를 경마 주제로 (`"경마 예상"`, `"경마 분석 실습"` 등 — **테스트해서 정한다**)
- `--topic horse-racing` 으로 저장 폴더 분리
- 새 SKILL.md 작성 (`horse-youtube-digest`)
- 새 cron 작업 등록

### 그대로 쓰는 것

- 한글 비율 계산, 기간 필터, 채널 제한, 조회수 비교 로직
- manifest·SHA-256 검증 패턴
- `youtube_daily.sh` 구조 (경로와 검색어만 수정)
- `data-collector`, `data-reviewer` 프로필

**검색어가 명령행 인자로 빠져 있어 코드는 거의 그대로다.** AGENTS.md에 "검색어와 기간은 하드코딩하지 않는다"고 적어둔 것이 여기서 값을 한다.

---

## 15. 다음 대화에 붙여넣을 재시작 프롬프트

```
나는 Windows 노트북에서 WSL2 Ubuntu 24.04를 사용하고 있다.
프로젝트 경로는 /home/geoheim/projects/youtube-digest 이다.

현재 완료 상태:
1. YouTube Data API v3 키를 발급받아 프로젝트 .env의 YOUTUBE_API_KEY에 저장했다.
   Gemini 키와 별개이며 제한이 YouTube Data API v3로 걸려 있다. 값은 출력하지 않는다.
2. scripts/youtube_collect_once.py가 검색어별로 최신순 25개를 받고
   videos API로 상세를 조회해 원본 JSON, manifest, SHA-256을 저장한다.
   1회 수집에 201 유닛을 쓴다. 일일 한도는 10,000이다.
3. scripts/youtube_digest.py가 저장된 원본만 읽어
   최근 7일 + 한국어 필터 → 채널당 2개 제한 → 조회수 정렬 → 상위 5개를 보고하고
   직전 수집과 비교해 조회수 변화를 계산한다. 새 API 호출을 하지 않는다.
4. 검색어는 '"AI 에이전트" 만들기' 와 'AI 에이전트 구축 실습' 두 개다.
   외래어만 있는 검색어(튜토리얼, 워크플로우)는 영어 결과만 나와서 탈락시켰다.
5. pytest 15 passed. tests/test_youtube_digest.py가 순수 함수를 검증한다.
6. 브랜치 main, 최신 커밋 52e4f7e, working tree clean.
7. .hermes/skills/youtube-digest/SKILL.md 스킬이 있다.
8. youtube 프로필을 만들어 terminal.cwd와 trusted_project_dirs를
   youtube-digest로 지정했다. 유튜브 대화는 'youtube chat'으로 한다.
9. ~/.hermes/scripts/youtube_daily.sh 를 cron이 매일 8시에 실행한다.
   작업 ID는 8b92e4108dcf, --no-agent 모드라 LLM을 거치지 않는다.
   결과는 Telegram home 채널과 ~/.hermes/cron/output/ 에 저장된다.
10. gateway는 systemd 사용자 서비스로 등록되어 있다. hermes gateway start 로 켠다.

주의사항:
- 100줄 넘는 파일은 터미널 붙여넣기로 만들지 않는다. 잘린다.
  파일로 받아서 cp 하는 방식을 쓴다.
- .env를 고친 뒤에는 source .env 를 다시 해야 한다.
- Gemini 503은 Google 서버 문제다. cron 경로는 LLM을 안 쓰므로 영향받지 않는다.
- WSL을 껐다 켜면 gateway가 죽을 수 있다.

재개할 때 먼저 실행할 명령:
cd ~/projects/youtube-digest
source .venv/bin/activate
git log --oneline -6
git status --short
pytest -q
hermes gateway status
hermes cron status

다음 작업:
- 이 구조를 KRA 프로젝트(horse-agent-free-laptop-starter)에 이식해
  경마 유튜브 보고를 만든다. 검색어는 테스트해서 정한다.
- 필요하면 LLM 요약(B안)으로 확장한다.

나에게 명령을 한꺼번에 많이 주지 말고, 한 단계씩 실행 결과를 확인하면서 코치해 줘.
API 키·토큰·비밀번호는 출력하거나 요구하지 마.
```

---

## 16. 용어 정리

| 용어 | 쉽게 말하면 | 이 프로젝트의 예 |
| --- | --- | --- |
| cron | 정해진 시각에 명령을 자동 실행 | 매일 8시 유튜브 보고 |
| crontab 표기 | `분 시 일 월 요일` | `0 8 * * *` = 매일 8시 |
| `--no-agent` | LLM을 건너뛰고 스크립트 출력만 전달 | 503과 무관하게 작동 |
| home 채널 | cron 결과를 배달할 Telegram 채팅 | `/sethome`으로 설정 |
| systemd 서비스 | 백그라운드에서 도는 프로그램 | gateway |
| linger | 로그아웃해도 서비스 유지 | gateway install 시 자동 |
| wrapper | 긴 명령의 줄임 스크립트 | `youtube` = `hermes --profile youtube` |
| `terminal.cwd` | 그 프로필이 일하는 폴더 | 프로필마다 다르다 |
| `trusted_project_dirs` | 스킬을 읽어올 프로젝트 폴더 | 프로필 config에 있다 |
| manifest | 수집한 것의 목록과 증명서 | 건수, 해시, 할당량 |
| 할당량(유닛) | API 사용량 계량 단위 | search 100, videos 1 |
| `.gitignore` | git이 무시할 파일 목록 | `.env`, `.venv/`, `data/raw/` |

---

## 17. 문서 갱신 원칙

- 중요 단계가 완료될 때마다 "현재 위치"와 "다음 작업"만 갱신한다.
- API 키·토큰·개인식별정보는 복사하지 않는다.
- Git 커밋 해시, 브랜치, pytest 결과, cron 작업 ID를 기록한다.
- **프로필·cron·gateway 설정은 Git 밖에 있으므로 이 문서가 유일한 재현 근거다.**
- 검색어를 바꾸면 5장에 그 이유와 테스트 결과를 남긴다.
- 마크다운을 원본으로 Git에 두고 PDF는 필요할 때 생성한다.
- 이 문서는 `docs/YOUTUBE_DIGEST_STATUS.md`에 두고 갱신 후 커밋한다.

---

*— 요약 끝 —*

*작성 2026-09-04 · 기준 커밋 `52e4f7e` · API 키·토큰은 문서에 포함하지 않음*
