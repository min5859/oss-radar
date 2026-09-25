# OSS Radar

GitHub에서 매주 주목할 만한 오픈소스 프로젝트를 자동 발굴·분석하여
GitHub Wiki에 한국어 리포트로 발행하는 파이프라인.

- **Wiki**: https://github.com/min5859/oss-radar/wiki
- **현재 스케줄**: 매일 05:00 KST (macOS launchd, OCI 이관 후 systemd)

---

## 아키텍처

```
discover.py → fetch.py → analyze.py → publish.py
  (레포선정)   (README수집)  (AI CLI분석)  (Wiki발행)
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

Wiki 발행 서버에서는 검색용 토큰과 쓰기용 자격증명을 분리합니다.

```bash
export GITHUB_WIKI_TOKEN="..."  # oss-radar Wiki 쓰기 전용
export OSS_RADAR_WIKI_URL="https://github.com/min5859/oss-radar.wiki.git"
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
python3 src/analyze.py     # 설정된 AI provider 분석 → data/analysis/
python3 src/publish.py     # Wiki 발행
```

게시 없이 Wiki 출력만 검증:

```bash
python3 src/publish.py --dry-run
OSS_RADAR_DRY_RUN=1 bash run.sh
```

`history.json`은 레포 선정 시점이 아니라 Wiki push가 성공한 뒤 갱신됩니다.
실패 실행으로 history가 앞서간 경우 다음 명령으로 점검한 뒤 복구할 수 있습니다.

```bash
python3 scripts/reconcile_history.py
python3 scripts/reconcile_history.py --apply
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

## OCI Linux 이관

OCI 준비, systemd 설치, 상태 파일 이관, 컷오버와 롤백 절차는
[`docs/OCI-MIGRATION.md`](docs/OCI-MIGRATION.md)를 따릅니다. 서비스와 timer
템플릿은 `docs/systemd/`에 있습니다. GitHub 자격증명 등록, Codex Device Code
승인, 기존 Mac 자동화 중지, OCI timer 활성화는 운영자가 직접 확인합니다.

---

## 설정 (`config.yaml`)

| 키 | 기본값 | 설명 |
|---|---|---|
| `repos.count` | 5 | 주당 선정 레포 수 |
| `repos.lookback_days` | 7 | 검색 기간 (일) |
| `repos.min_stars` | 100 | 최소 star 수 필터 |
| `categories` | ai, developer-tools, productivity | 관심 카테고리 |
| `wiki.repo` | min5859/oss-radar | Wiki 발행 대상 레포 |
| `analysis.provider` | codex | 분석 CLI provider (`claude`, `codex`, `cursor`) |
| `analysis.<provider>.model` | provider별 설정 | 비어 있으면 CLI 기본 모델 |

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
│   ├── analyze.py         # Claude/Codex/Cursor 분석 호출
│   └── publish.py         # GitHub Wiki 발행
├── scripts/
│   └── reconcile_history.py  # 발행 Wiki 기준 history 복구
├── docs/
│   ├── OCI-MIGRATION.md
│   └── systemd/           # Linux service/timer/env 템플릿
├── prompts/
│   └── analyze.md         # Claude 분석 프롬프트
├── config/
│   └── com.wooki.oss-radar.plist  # macOS launchd 설정
├── data/                  # 런타임 생성 (gitignore)
└── logs/                  # 런타임 생성 (gitignore)
```
