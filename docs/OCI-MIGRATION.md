# OSS Radar OCI 운영 서버 이관 런북

이 문서는 macOS에서 실행 중인 OSS Radar를 OCI Linux 서버로 안전하게 옮기는
절차와 실제 진행 상태를 기록합니다. 다른 단일 호스트 자동화 프로젝트에도 적용할
수 있도록 준비, 검증, 컷오버, 롤백을 분리합니다.

## 1. 목표와 완료 조건

운영 구조는 다음과 같습니다.

```text
OCI systemd timer (현재 기준 매일 05:00 KST)
  -> /srv/oss-radar/run.sh
  -> GitHub 후보 수집 및 AI 분석
  -> min5859/oss-radar Wiki push
```

완료 조건:

- 전용 `ossradar` 사용자로 Python, Git, Codex CLI가 실행됩니다.
- Search API 읽기 자격증명과 Wiki 쓰기 자격증명이 분리되어 있습니다.
- `history.json`은 실제 발행된 레포만 포함합니다.
- 게시 없는 dry-run과 Wiki push dry-run이 성공합니다.
- Mac LaunchAgent와 OCI timer가 동시에 활성화되지 않습니다.
- OCI 자동 실행이 2회 연속 성공합니다.

## 2. 확인된 환경과 이전 이관에서 재사용할 패턴

2026-09-25 읽기 전용 점검 결과:

- OCI: Ubuntu 24.04.4 LTS, ARM64, RAM 23GiB, 루트 디스크 여유 24GB
- 서버 시간대: UTC, NTP 동기화 정상
- `/srv/dev-blog`의 전용 사용자와 systemd timer 운영 패턴이 정상 작동 중
- Node.js 24.18.0과 Python 3.12.3 사용 가능
- `dev-blog.timer`는 `Asia/Seoul`을 명시해 서버 UTC 설정과 무관하게 동작
- 저장소별 deploy key는 연결된 본 저장소에는 접근하지만 Wiki 저장소에는
  접근하지 못함을 실측

재사용할 원칙:

1. 프로젝트별 Linux 사용자와 `/srv/<project>` 작업 디렉터리를 사용합니다.
2. AI CLI 인증과 systemd 실행 사용자의 HOME을 일치시킵니다.
3. timer를 켜기 전에 게시 없는 검증을 마칩니다.
4. 기존 writer를 먼저 끄고 새 writer를 켭니다.
5. timer는 최초 이관 시 `Persistent=false`로 두어 예기치 않은 catch-up을 막습니다.

## 3. 이번 이관에서 발견하고 보강한 문제

### 발행 전 history 갱신

기존 `discover.py`는 후보를 선정한 직후 `history.json`에 추가했습니다. 분석이나
Wiki push가 실패하면 발행되지 않은 레포도 영구 제외되는 구조였습니다.

수정 후에는 `publish.py`가 Wiki push 성공 뒤에만 history를 원자적으로 갱신합니다.
복구 도구는 발행된 Wiki 페이지에서 레포 이름을 추출해 history와 대조합니다.

```bash
python3 scripts/reconcile_history.py
python3 scripts/reconcile_history.py --apply
```

`--apply`는 기존 파일을 `history.json.backup-YYYYMMDD-HHMMSS`로 보존합니다.

### 진단 불가능한 Codex 오류

기존 구현은 stderr의 첫 200자만 기록해 Codex 헤더 뒤의 실제 오류가 사라졌습니다.
수정 후 종료 코드와 stderr 마지막 4,000자를 기록합니다. 2026-09-14부터 발생한
실패 당시 CLI는 0.150.1이었고, 0.157.0 업데이트 후 동일 smoke test가 성공했습니다.

### 안전하지 않은 Wiki clone 복구

기존 코드는 pull 실패 시 `data/wiki_clone`을 자동 삭제했습니다. 이제 기존 clone을
보존하고 실패하므로 인증 문제와 로컬 미푸시 commit을 조사할 수 있습니다.

### GitHub 인증 분리

- `GITHUB_TOKEN`: Search API 읽기 전용
- `GITHUB_WIKI_TOKEN`: `oss-radar` Wiki 쓰기 전용
- `OSS_RADAR_WIKI_URL`: 자격증명이 들어 있지 않은 HTTPS URL

Wiki 토큰은 URL이나 명령 인자에 넣지 않습니다. `publish.py`가 Git subprocess에만
일시적인 HTTP Authorization header로 전달합니다.

## 4. 자동 처리 가능한 OCI 준비

다음 작업은 게시나 스케줄 활성화를 하지 않으므로 사전 수행할 수 있습니다.

```bash
id ossradar || sudo useradd --create-home --shell /bin/bash ossradar
sudo install -d -o ossradar -g ossradar -m 0755 /srv/oss-radar

sudo -u ossradar -H git clone \
  https://github.com/min5859/oss-radar.git /srv/oss-radar
sudo -u ossradar -H python3 -m venv /srv/oss-radar/.venv
sudo -u ossradar -H /srv/oss-radar/.venv/bin/pip install \
  -r /srv/oss-radar/requirements.txt
```

Codex CLI는 공식 standalone installer를 내려받아 내용을 확인한 뒤 `ossradar`
사용자로 설치합니다.

```bash
sudo -u ossradar -H bash -lc \
  'curl -fsSL https://chatgpt.com/codex/install.sh | sh'
sudo -u ossradar -H /home/ossradar/.local/bin/codex --version
```

`sudo -u` 실행 전 현재 디렉터리가 `/home/ubuntu`처럼 `ossradar`가 접근할 수 없는
경로이면 installer 내부 `find`가 실패할 수 있습니다. 반드시 대상 사용자 HOME으로
이동한 셸에서 실행합니다.

```bash
sudo -u ossradar -H bash -c \
  'cd "$HOME" && bash /tmp/oss-radar-codex-install.sh'
```

systemd 파일은 설치하되 아직 timer를 활성화하지 않습니다.

```bash
sudo install -o root -g root -m 0644 \
  /srv/oss-radar/docs/systemd/oss-radar.service \
  /etc/systemd/system/oss-radar.service
sudo install -o root -g root -m 0644 \
  /srv/oss-radar/docs/systemd/oss-radar.timer \
  /etc/systemd/system/oss-radar.timer
sudo systemctl daemon-reload
sudo systemd-analyze verify \
  /etc/systemd/system/oss-radar.service \
  /etc/systemd/system/oss-radar.timer
```

## 5. 운영자가 직접 해야 하는 작업

### 5.1 GitHub 자격증명

1. Search API용 읽기 전용 토큰을 준비합니다.
2. `min5859/oss-radar`만 대상으로 하고 Wiki push가 가능한 최소 권한의
   자격증명을 준비합니다.
3. OCI의 `/srv/oss-radar/config/.env`에 입력합니다.

```bash
sudo install -o ossradar -g ossradar -m 0600 \
  /srv/oss-radar/docs/systemd/oss-radar.env.example \
  /srv/oss-radar/config/.env
sudoedit /srv/oss-radar/config/.env
```

토큰 값은 저장소, 터미널 출력, 대화 또는 journal에 남기지 않습니다.

### 5.2 Codex Device Code 승인

공식 OpenAI 문서는 headless 환경에서 Device Code 로그인을 우선 권장합니다.

```bash
sudo -u ossradar -H \
  /home/ossradar/.local/bin/codex login --device-auth
sudo -u ossradar -H \
  /home/ossradar/.local/bin/codex login status
```

표시된 URL과 일회용 코드는 운영자가 브라우저에서 승인합니다. 인증 캐시는 비밀로
취급하고 저장소에 복사하지 않습니다.

### 5.3 컷오버 승인

다음 두 작업은 중복 발행을 막기 위해 같은 컷오버 창에서 직접 확인합니다.

```bash
# Mac
launchctl bootout \
  "gui/$(id -u)" \
  /Users/wooki/Library/LaunchAgents/com.wooki.oss-radar.plist

# OCI — Mac 중지 확인 후
sudo systemctl enable --now oss-radar.timer
```

## 6. 게시 없는 검증

코드가 OCI에 반영된 뒤 다음 순서로 확인합니다.

```bash
sudo -u ossradar -H /srv/oss-radar/.venv/bin/python \
  -m unittest discover -s /srv/oss-radar/tests -v
sudo -u ossradar -H /srv/oss-radar/.venv/bin/python \
  -m compileall -q /srv/oss-radar/src
sudo -u ossradar -H env OSS_RADAR_DRY_RUN=1 \
  /srv/oss-radar/run.sh
```

마지막 명령은 수집과 분석까지 수행하지만 Wiki push와 history 갱신은 하지 않습니다.
Wiki 쓰기 인증은 별도로 기존 clone 또는 임시 clone에서 `git push --dry-run`으로
확인합니다. 다음 명령은 `.env`를 현재 셸에만 로드하고, 임시 clone을 제거한 뒤
종료합니다. 토큰은 URL이나 명령 인자에 포함되지 않습니다.

```bash
sudo -u ossradar -H bash -c '
  set -a
  source /srv/oss-radar/config/.env
  set +a
  /srv/oss-radar/.venv/bin/python \
    /srv/oss-radar/scripts/check_wiki_access.py
'
```

## 7. 스케줄 선택

현재 Mac의 실제 운영값을 보존해 기본 timer는 매일 05:00 KST입니다.

```ini
OnCalendar=*-*-* 05:00:00 Asia/Seoul
```

본래 프로젝트 설명대로 주간 발행으로 바꾸려면 timer를 다음과 같이 수정합니다.

```ini
OnCalendar=Mon *-*-* 09:00:00 Asia/Seoul
```

수정 후에는 반드시 확인합니다.

```bash
sudo systemctl daemon-reload
systemd-analyze calendar '*-*-* 05:00:00 Asia/Seoul'
systemctl list-timers oss-radar.timer
```

## 8. 첫 실행 확인

```bash
systemctl status oss-radar.service --no-pager
systemctl show oss-radar.service \
  -p Result -p ExecMainStatus -p ActiveState -p InactiveExitTimestamp
journalctl -u oss-radar.service --since '-2 hours' --no-pager
systemctl list-timers oss-radar.timer
sudo -u ossradar -H git -C /srv/oss-radar status --short
```

추가로 오늘자 Wiki 페이지, `Home.md`, `data/history.json` 증가분을 확인합니다.
2회 연속 자동 실행 성공 후 이관 완료로 판정합니다.

## 9. 롤백

OCI writer를 먼저 중지합니다.

```bash
sudo systemctl disable --now oss-radar.timer
sudo systemctl stop oss-radar.service
```

실행 중 생성된 파일이나 Wiki clone의 미푸시 commit을 임의로 지우지 않습니다.
OCI 중지를 확인한 뒤에만 Mac LaunchAgent를 다시 등록합니다.

## 10. 다른 프로젝트에 적용할 체크리스트

1. 실제 실행 주기와 문서의 주기가 같은지 확인합니다.
2. 런타임 상태 중 반드시 옮길 파일과 재생성할 파일을 구분합니다.
3. 성공 전에 durable state를 갱신하는 코드가 없는지 확인합니다.
4. 읽기 자격증명과 게시 자격증명을 분리합니다.
5. 전용 OS 사용자, 고정 HOME, 명시적 PATH를 사용합니다.
6. 서비스와 timer 설치, 인증, 컷오버를 별도 단계로 나눕니다.
7. dry-run과 push dry-run 후 기존 writer를 중지합니다.
8. 새 writer를 활성화하고 2회 연속 성공을 확인합니다.
9. 롤백 시 새 writer를 먼저 끈다는 순서를 문서화합니다.

## 11. 진행 기록

### 2026-09-25 사전 조사

- 기존 `dev-blog` OCI 이관 문서와 실제 systemd 운영 상태 확인
- OCI 용량, OS, 아키텍처, Python/Node 설치 상태 확인
- `oss-radar` Mac LaunchAgent가 실제로 매일 05:00에 실행됨을 확인
- 2026-09-14부터 12회 연속 분석 실패, 마지막 발행 2026-09-13 확인
- history 700개 중 실제 Wiki 발행 600개, 미발행 100개 확인
- Codex CLI 0.157.0으로 동일 호출 smoke test 성공

### 2026-09-25 코드 및 로컬 상태 보강

- history 갱신 시점을 Wiki push 성공 이후로 이동
- history 원자적 저장과 Wiki 기준 복구 도구 추가
- 기존 history를 백업한 뒤 700개에서 실제 발행된 600개로 복구
- Codex 실패 로그를 종료 코드와 stderr tail 중심으로 개선
- `publish.py --dry-run`과 `OSS_RADAR_DRY_RUN=1` 추가
- Wiki token을 URL/argv에 넣지 않는 Git subprocess 인증 경로 추가
- pull 실패 시 기존 Wiki clone을 삭제하지 않도록 변경
- 전체 dry-run 성공: 후보 5개 수집, README 5개, Codex 분석 5개,
  Wiki 출력 검증 완료; history 600개와 Wiki commit은 불변

### 2026-09-25 OCI 사전 준비

- `ossradar` 사용자와 `/srv/oss-radar` checkout 생성
- Python 3.12 가상환경과 프로젝트 의존성 설치
- 공식 standalone installer로 ARM64 Codex CLI 0.157.0 설치
- 복구된 history 600개를 SHA-256 일치 확인 후 전송
- `/srv/oss-radar/config/.env` 비밀값 없는 템플릿 설치(0600 ossradar)
- systemd service/timer 설치와 `systemd-analyze verify` 완료
- `oss-radar.timer`는 `disabled`, `inactive` 상태로 유지
- 변경 내용을 `origin/main`에 push하고 OCI checkout을 fast-forward
- OCI에서 단위 테스트 5개, Python compileall, `bash -n` 통과
- 설치된 systemd 파일과 저장소 템플릿의 SHA-256 일치 확인
- systemd와 수동 실행이 같은 `config/.env`를 읽도록 통일
- 남은 사용자 작업: GitHub 토큰 입력, Codex Device Code 승인, 전체 dry-run,
  Mac 중지, OCI timer 활성화

### 안전 경계

다음은 운영자 확인 전 수행하지 않습니다.

- GitHub 토큰 생성 또는 계정 설정 변경
- Codex Device Code 브라우저 승인
- Mac LaunchAgent 중지
- OCI timer 활성화
- 실제 Wiki 게시 실행
