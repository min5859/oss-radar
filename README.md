# OSS Radar

GitHub에서 매주 주목할 만한 오픈소스 프로젝트를 자동 발굴·분석하여
GitHub Wiki에 한국어 리포트로 발행하는 파이프라인.

- **Wiki**: https://github.com/min5859/oss-radar/wiki
- **스케줄**: 매주 월요일 09:00 KST (macOS launchd)

---

## 아키텍처

```
discover.py → fetch.py → analyze.sh → publish.py
  (레포선정)   (README수집)  (Claude분석)  (Wiki발행)
```

---

## 셋업

### 1. 의존성 설치

```bash
cd ~/project/toy/oss-radar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
export GITHUB_TOKEN="ghp_..."   # 권장: rate limit 향상 (없으면 60 req/h)
```

### 3. GitHub Token 설정 (선택)

`~/.zshrc` 또는 `~/.bash_profile`에 추가:

```bash
export GITHUB_TOKEN="ghp_..."
```

---

## 실행

### 전체 파이프라인

```bash
bash run.sh
```

### 개별 단계

```bash
python3 src/discover.py    # 레포 선정 → data/repos.json
python3 src/fetch.py       # README 수집 → data/repos.json 업데이트
bash src/analyze.sh        # Claude 분석 → data/analysis/
python3 src/publish.py     # Wiki 발행
```

---

## 자동화 설치 (macOS launchd)

```bash
cp config/com.wooki.oss-radar.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.wooki.oss-radar.plist
```

제거:

```bash
launchctl unload ~/Library/LaunchAgents/com.wooki.oss-radar.plist
rm ~/Library/LaunchAgents/com.wooki.oss-radar.plist
```

---

## 설정 (`config.yaml`)

| 키 | 기본값 | 설명 |
|---|---|---|
| `repos.count` | 5 | 주당 선정 레포 수 |
| `repos.lookback_days` | 7 | 검색 기간 (일) |
| `repos.min_stars` | 100 | 최소 star 수 필터 |
| `categories` | ai, developer-tools, productivity | 관심 카테고리 |
| `wiki.repo` | min5859/oss-radar | Wiki 발행 대상 레포 |
| `analysis.model` | sonnet | Claude 모델 |

---

## 파일 구조

```
oss-radar/
├── config.yaml            # 설정
├── requirements.txt       # Python 의존성
├── run.sh                 # 전체 파이프라인 실행
├── src/
│   ├── discover.py        # 레포 발굴 및 선정
│   ├── fetch.py           # README 및 메타데이터 수집
│   ├── analyze.sh         # Claude 분석 호출
│   └── publish.py         # GitHub Wiki 발행
├── prompts/
│   └── analyze.md         # Claude 분석 프롬프트
├── config/
│   └── com.wooki.oss-radar.plist  # macOS launchd 설정
├── data/                  # 런타임 생성 (gitignore)
└── logs/                  # 런타임 생성 (gitignore)
```
