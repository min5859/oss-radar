# AGENTS.md — oss-radar

## 프로젝트 목적

GitHub에서 매주 주목할 만한 오픈소스 프로젝트를 자동 발굴·분석하여
GitHub Wiki에 한국어 리포트로 발행하는 파이프라인.

- Wiki: https://github.com/min5859/oss-radar/wiki (배포 후 설정)
- 스케줄: 매주 월요일 09:00 KST (macOS launchd)

---

## 아키텍처

5단계 선형 파이프라인. research-wiki와 동일한 설계 원칙.

```
discover.py → fetch.py → analyze.sh → publish.py
  (레포선정)   (README수집)  (Claude분석)  (Wiki발행)
```

각 단계는 `data/` 내 파일을 읽고 쓰며 다음 단계에 전달한다.

### 단계별 역할

| 단계 | 입력 | 출력 | 설명 |
|---|---|---|---|
| `discover.py` | `config.yaml`, `data/history.json` | `data/repos.json` | GitHub에서 후보 레포 수집 및 점수화, 상위 N개 선정 |
| `fetch.py` | `data/repos.json` | `data/repos.json` (업데이트) | 각 레포의 README·메타데이터 수집 |
| `analyze.sh` | `data/repos.json` | `data/analysis/{owner}_{repo}.md` | Claude CLI로 한국어 분석 리포트 생성 |
| `publish.py` | `data/repos.json`, `data/analysis/` | GitHub Wiki | 분석 결과를 Wiki 페이지로 발행 |

---

## 데이터 소스

### 1. GitHub Search API (주력)
- 최근 7일 내 생성 또는 업데이트된 레포 검색
- 기준: star 증가 속도, fork 수, 언어, 토픽
- 인증: `GITHUB_TOKEN` 환경변수 (rate limit: 5000 req/h)

### 2. GitHub Trending (보조)
- `https://github.com/trending` HTML 스크래핑
- 일별·주별·월별 트렌딩 레포 수집

### 3. Hacker News (선택)
- "Show HN" 게시물 중 GitHub URL 포함된 것 필터링
- HN Algolia API: `https://hn.algolia.com/api/v1/search`

---

## 스코어링 기준

```
score = star_velocity * 0.5 + star_total_norm * 0.3 + fork_norm * 0.2
```

- `star_velocity`: 최근 7일 star 증가 수 (GitHub Archive 또는 delta 추정)
- `star_total_norm`: 전체 star 수 정규화
- `fork_norm`: fork 수 정규화
- HN 보너스: HN 게시물이 있으면 +0.1

---

## 분석 내용 (Claude가 생성)

각 레포에 대해 아래 항목을 한국어로 작성:

1. **한줄 요약** — 이 프로젝트가 무엇인지 한 문장
2. **주요 기능** — 핵심 기능 3~5가지 bullet
3. **사용 시나리오** — 실제 어떤 상황에서 쓸 수 있는지
4. **기술 스택** — 언어, 의존성, 아키텍처 특징
5. **주목 이유** — 왜 이번 주 주목받고 있는지 (트렌드 맥락)
6. **실용성 평가** — 즉시 쓸 수 있는지, 성숙도, 주의점

---

## 설정 파일 (`config.yaml`)

```yaml
repos:
  count: 5              # 주당 선정 레포 수
  lookback_days: 7      # 검색 기간
  min_stars: 100        # 최소 star 수 필터

categories:             # 관심 카테고리 (비어있으면 전체)
  - ai
  - developer-tools
  - productivity

sources:
  github_search:
    enabled: true
    weight: 0.6
  github_trending:
    enabled: true
    weight: 0.4
  hacker_news:
    enabled: false
    weight: 0.0

wiki:
  repo: "min5859/oss-radar"

analysis:
  language: "ko"
  prompt_file: "prompts/analyze.md"
  model: "sonnet"
```

---

## 핵심 설계 결정

- **멱등성**: 각 단계에서 출력 파일이 이미 존재하면 스킵 (재실행 안전)
- **history.json**: 이전에 분석한 레포 전체 이름 (`owner/repo`) 기록으로 중복 방지
- **rate limit 대응**: GitHub API는 최소 1초 간격으로 호출, retry with backoff
- **README 길이 제한**: 40,000자 초과 시 truncate (Claude 컨텍스트 절약)
- **분석 호출**: `env -u CLAUDECODE claude -p` — 중첩 세션 방지
- **bkit footer 제거**: analyze.sh에서 Claude 출력의 bkit 보고 블록을 sed로 자동 제거
- **언어 검증**: 분석 출력이 한국어인지 확인, 아니면 최대 2회 재시도

---

## 파일 구조

```
oss-radar/
├── AGENTS.md              # 이 파일
├── CLAUDE.md              # Claude Code 지침
├── config.yaml            # 설정
├── requirements.txt       # Python 의존성
├── run.sh                 # 전체 파이프라인 실행 스크립트
├── src/
│   ├── discover.py        # 레포 발굴 및 선정
│   ├── fetch.py           # README 및 메타데이터 수집
│   ├── analyze.sh         # Claude 분석 호출
│   └── publish.py         # GitHub Wiki 발행
├── prompts/
│   └── analyze.md         # Claude 분석 프롬프트 템플릿
├── data/                  # 런타임 생성 (gitignore)
│   ├── repos.json         # 선정된 레포 메타데이터
│   ├── history.json       # 분석 완료 레포 기록
│   └── analysis/          # 레포별 분석 마크다운
├── logs/                  # 런타임 생성 (gitignore)
└── config/
    └── com.wooki.oss-radar.plist  # macOS launchd 설정
```

---

## Commands

```bash
# 전체 파이프라인 실행
bash run.sh

# 개별 단계 실행
python3 src/discover.py    # 레포 선정 → data/repos.json
python3 src/fetch.py       # README 수집 → data/repos.json 업데이트
bash src/analyze.sh        # Claude 분석 → data/analysis/
python3 src/publish.py     # Wiki 발행

# 의존성 설치
pip install -r requirements.txt
```

---

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `GITHUB_TOKEN` | 권장 | GitHub API rate limit 향상 (없으면 60 req/h) |
| `ANTHROPIC_API_KEY` | 선택 | cron 환경에서 Claude 인증용 |

---

## Working Rules for Agents

- 이 파일을 먼저 읽고 설계 결정을 준수할 것
- research-wiki의 패턴(로깅, 멱등성, fallback)을 그대로 따를 것
- config.yaml에 없는 하드코딩 값은 금지
- 커밋은 단일 논리 단위로 스코프를 좁게 유지
- 완료 보고 전에 타입/린트 오류 없는지 확인
