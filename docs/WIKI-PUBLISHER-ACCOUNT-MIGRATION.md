# Wiki Publisher 서비스 계정 마이그레이션 계획

## 1. 목적

OCI에서 Wiki 게시 자동화를 프로젝트별 계정 대신 공용 서비스 계정으로 운영합니다.
첫 단계에서는 기존 `ossradar` 계정의 UID/GID와 인증 상태를 보존하면서 이름과
홈만 `wiki-publisher`로 변경합니다.

```text
Before
  ossradar (UID/GID 1003)
  /home/ossradar
  /srv/oss-radar

After
  wiki-publisher (UID/GID 1003)
  /home/wiki-publisher
  /srv/oss-radar
```

## 2. 범위

이번 작업에 포함합니다.

- `ossradar` 사용자와 기본 그룹 이름 변경
- 홈 디렉터리 이동
- Cursor/Codex 실행 symlink와 셸 PATH 복구
- OSS Radar systemd service의 사용자·HOME·PATH 변경
- Cursor 로그인, GitHub 인증, 테스트, 전체 dry-run 검증
- 검증 성공 후 기존 timer 상태 복구

이번 작업에 포함하지 않습니다.

- `devblog` 계정 또는 `/srv/dev-blog` 변경
- `research-wiki` 배포
- 프로젝트별 GitHub 토큰 통합
- 기존 계정이나 홈 데이터 삭제

## 3. 사전 확인 상태

2026-09-27 기준:

- `ossradar`: UID/GID 1003, 홈 `/home/ossradar`
- `/home/wiki-publisher`: 존재하지 않음
- `/srv/oss-radar`: `ossradar:ossradar` 소유
- `oss-radar.timer`: enabled/active
- 최근 `oss-radar.service`: exit 0
- 실행 중인 `ossradar` 프로세스: 없음
- Cursor Agent: `2026.09.26-dd393fe`, 로그인 정상
- Git worktree: clean, `main`과 `origin/main` 일치

## 4. 성공 조건

- `wiki-publisher`의 UID/GID가 기존 값 1003을 유지합니다.
- `ossradar` 사용자와 그룹 이름이 더 이상 남지 않습니다.
- `/home/wiki-publisher`로 홈 전체가 이동됩니다.
- `/srv/oss-radar`의 수치 UID/GID와 데이터가 바뀌지 않습니다.
- Cursor Agent 실행과 기존 로그인이 유지됩니다.
- GitHub Wiki 인증 점검과 전체 dry-run이 성공합니다.
- systemd가 `wiki-publisher` 사용자로 검증·실행됩니다.
- 실패 시 timer가 켜지지 않으며 아래 롤백 절차로 복구할 수 있습니다.

## 5. 주요 위험과 대응

### 절대경로 symlink

현재 다음 symlink는 `/home/ossradar`를 절대경로로 가리킵니다.

```text
~/.local/bin/agent
~/.local/bin/cursor-agent
~/.local/bin/codex
```

홈 이동 후 새 HOME 기준으로 target 존재를 확인하고 symlink를 다시 연결합니다.

### 실행 중 계정 변경

사용자 이름 변경 전에 `oss-radar.timer`와 service를 중지하고 해당 UID의 프로세스가
없는지 다시 확인합니다. 검증이 끝날 때까지 timer를 활성화하지 않습니다.

### 인증 캐시

Cursor 인증 캐시는 `/home/ossradar/.config/cursor/auth.json`에 있습니다. 홈 전체를
같은 UID로 이동하므로 파일 소유권과 내용은 유지합니다. 변경 전 root 전용 백업을
만들고 변경 후 `agent status`로 확인합니다.

## 6. 실행 절차

### 6.1 중지와 백업

```bash
sudo systemctl disable --now oss-radar.timer
sudo systemctl stop oss-radar.service
pgrep -a -u ossradar

sudo install -d -o root -g root -m 0700 /var/backups/wiki-publisher
sudo tar -czf /var/backups/wiki-publisher/ossradar-critical-home.tar.gz \
  -C /home/ossradar .config/cursor .ssh .gitconfig .bashrc .local/bin
sudo cp -a /etc/systemd/system/oss-radar.service \
  /var/backups/wiki-publisher/oss-radar.service.before
```

존재하지 않는 선택 파일은 실제 백업 명령에서 제외합니다. 백업 파일은 0600으로
제한하고 비밀값을 출력하지 않습니다.

### 6.2 사용자·그룹·홈 이름 변경

```bash
sudo usermod -l wiki-publisher ossradar
sudo groupmod -n wiki-publisher ossradar
sudo usermod -d /home/wiki-publisher -m wiki-publisher
```

UID/GID 1003이 유지되는지 즉시 확인합니다.

### 6.3 홈 내부 절대경로 복구

- `.bashrc`의 `/home/ossradar`를 `/home/wiki-publisher`로 변경
- `.local/bin/agent`, `cursor-agent`, `codex` symlink를 새 HOME 기준으로 재연결
- 깨진 symlink와 남은 활성 설정 참조를 검사

과거 로그 안의 문자열은 실행 설정이 아니므로 수정하지 않습니다.

### 6.4 systemd 변경

저장소 템플릿과 설치된 unit을 다음 값으로 변경합니다.

```ini
User=wiki-publisher
Group=wiki-publisher
Environment=HOME=/home/wiki-publisher
Environment=PATH=/home/wiki-publisher/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStartPre=/usr/bin/test -x /home/wiki-publisher/.local/bin/agent
```

```bash
sudo systemctl daemon-reload
sudo systemd-analyze verify \
  /etc/systemd/system/oss-radar.service \
  /etc/systemd/system/oss-radar.timer
```

### 6.5 검증

```bash
sudo -u wiki-publisher -H /home/wiki-publisher/.local/bin/agent status
sudo -u wiki-publisher -H git -C /srv/oss-radar status --short
sudo -u wiki-publisher -H /srv/oss-radar/.venv/bin/python \
  -m unittest discover -s /srv/oss-radar/tests -v
sudo -u wiki-publisher -H env OSS_RADAR_DRY_RUN=1 \
  /srv/oss-radar/run.sh
```

Wiki 인증 점검, 테스트, dry-run, worktree clean을 모두 통과한 뒤에만 timer를 기존
상태로 복구합니다.

```bash
sudo systemctl enable --now oss-radar.timer
systemctl list-timers oss-radar.timer
```

## 7. 롤백

검증에 실패하면 timer를 끈 상태로 유지하고 역순으로 복구합니다.

```bash
sudo usermod -d /home/ossradar -m wiki-publisher
sudo groupmod -n ossradar wiki-publisher
sudo usermod -l ossradar wiki-publisher
sudo cp -a /var/backups/wiki-publisher/oss-radar.service.before \
  /etc/systemd/system/oss-radar.service
sudo systemctl daemon-reload
sudo systemd-analyze verify \
  /etc/systemd/system/oss-radar.service \
  /etc/systemd/system/oss-radar.timer
```

Cursor 설정 복구가 필요하면 root 전용 백업과 현재 파일을 먼저 비교하며, 홈 전체를
덮어쓰지 않습니다. 롤백 검증 후에만 timer를 다시 활성화합니다.

## 8. 후속 단계

OSS Radar가 새 계정으로 정상 자동 실행되는 것을 확인한 뒤 별도 계획으로 진행합니다.

1. `/srv/dev-blog`와 GitHub deploy key를 `wiki-publisher`로 이전
2. `dev-blog.service`의 실행 사용자 변경
3. 2회 이상 정상 실행 후 `devblog` 계정 비활성화
4. `/srv/research-wiki` 배포 및 별도 service/timer 구성

프로젝트별 `.env`, GitHub 토큰, 로그, systemd unit은 통합하지 않습니다.
