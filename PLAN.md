# oss-radar 구현 계획

## 목표
GitHub에서 매주 주목할 만한 오픈소스 프로젝트를 자동 발굴·분석하여
GitHub Wiki에 한국어 리포트로 발행하는 파이프라인.

---

## Phase 1 — 프로젝트 기반 셋업
**목표:** 실행 가능한 뼈대 구성

- [ ] `config.yaml` — 설정 파일 (레포 수, 기간, 소스 가중치, Wiki 설정)
- [ ] `requirements.txt` — Python 의존성 (requests, PyYAML, beautifulsoup4)
- [ ] `.gitignore` — data/, logs/, .venv/ 등 제외
- [ ] `run.sh` — 전체 파이프라인 실행 스크립트
- [ ] `prompts/analyze.md` — Claude 분석 프롬프트 템플릿
- [ ] git 커밋

---

## Phase 2 — GitHub 레포 발굴 (`src/discover.py`)
**목표:** 주목할 레포 선정 → `data/repos.json`

- [ ] GitHub Search API — 최근 7일 star 급상승 레포 수집
- [ ] GitHub Trending 페이지 스크래핑 (github.com/trending)
- [ ] 스코어링: `star_velocity×0.5 + star_total_norm×0.3 + fork_norm×0.2`
- [ ] `data/history.json` 로 중복 방지
- [ ] 상위 N개 선정 → `data/repos.json` 저장
- [ ] git 커밋

---

## Phase 3 — README 및 메타데이터 수집 (`src/fetch.py`)
**목표:** 각 레포의 README·상세 메타데이터 수집 → `data/repos.json` 업데이트

- [ ] GitHub API `/repos/{owner}/{repo}` — 기본 메타데이터
- [ ] GitHub API `/repos/{owner}/{repo}/readme` — README 원문 (base64 디코딩)
- [ ] 40,000자 초과 시 truncate
- [ ] 언어, 토픽, 라이선스 보강
- [ ] `data/repos.json` 필드 업데이트
- [ ] git 커밋

---

## Phase 4 — Claude 분석 (`src/analyze.sh`)
**목표:** 레포별 한국어 분석 리포트 → `data/analysis/{owner}_{repo}.md`

- [ ] research-wiki `analyze.sh` 패턴 기반
- [ ] 레포별 루프: repos.json 순회
- [ ] `env -u CLAUDECODE claude -p` 호출 (중첩 세션 방지)
- [ ] 한국어 출력 검증 + 최대 2회 재시도
- [ ] bkit footer 자동 제거 (sed)
- [ ] git 커밋

---

## Phase 5 — GitHub Wiki 발행 (`src/publish.py`)
**목표:** 분석 결과를 주간 Wiki 페이지로 발행

- [ ] research-wiki `publish.py` 패턴 기반
- [ ] 주간 리포트 마크다운 빌드 (레포별 분석 합산)
- [ ] `data/wiki_clone/` git clone → 페이지 추가 → push
- [ ] Wiki 페이지 명명: `YYYY-MM-DD-Weekly-OSS-Radar.md`
- [ ] git 커밋

---

## Phase 6 — 자동화 & 마감
**목표:** 주간 자동 실행 및 문서화

- [ ] `config/com.wooki.oss-radar.plist` — macOS launchd 설정
- [ ] `README.md` — 셋업 가이드 및 사용법
- [ ] 전체 파이프라인 수동 테스트
- [ ] git 커밋

---

## 참고
- 기반 프로젝트: `/Users/wooki/project/toy/research-wiki`
- 설계 상세: `AGENTS.md`
