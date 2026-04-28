#!/usr/bin/env bash
# Analyze GitHub repos using Claude CLI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
REPOS_FILE="$ROOT/data/repos.json"
ANALYSIS_DIR="$ROOT/data/analysis"
LOG_FILE="$ROOT/logs/analyze.log"

# Read config values from config.yaml
PROMPT_FILE="$ROOT/$(python3 -c "import yaml; print(yaml.safe_load(open('$ROOT/config.yaml'))['analysis'].get('prompt_file', 'prompts/analyze.md'))")"
MAX_RETRIES=$(python3 -c "import yaml; print(yaml.safe_load(open('$ROOT/config.yaml'))['analysis'].get('max_retries', 2))")
MODEL=$(python3 -c "import yaml; print(yaml.safe_load(open('$ROOT/config.yaml'))['analysis'].get('model', 'sonnet'))")

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $*" | tee -a "$LOG_FILE"
}

# OS-aware sed -i
sed_inplace() {
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# Check if output contains Korean characters (Hangul syllables, min 10)
has_korean() {
    python3 -c "
import sys, re
text = open(sys.argv[1], encoding='utf-8').read()
if re.search(r'[\uAC00-\uD7A3]', text) and len(re.findall(r'[\uAC00-\uD7A3]', text)) >= 10:
    sys.exit(0)
else:
    sys.exit(1)
" "$1"
}

# Strip bkit footer from output file
strip_bkit_footer() {
    local file="$1"
    if grep -q "^─.*bkit Feature Usage" "$file" 2>/dev/null; then
        sed_inplace '/^─.*bkit Feature Usage/,$d' "$file"
        sed_inplace -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$file"
    fi
}

# Ensure claude CLI is in PATH (cron doesn't load user profile)
export PATH="$HOME/.local/bin:$PATH"

mkdir -p "$ANALYSIS_DIR"

if [ ! -f "$REPOS_FILE" ]; then
    error "repos.json not found. Run discover.py and fetch.py first."
    exit 1
fi

# Pre-flight: verify claude CLI is available and authenticated
if ! command -v claude &>/dev/null; then
    error "claude CLI not found in PATH: $PATH"
    exit 1
fi

log "Checking claude CLI authentication (model: $MODEL)..."
if env -u CLAUDECODE claude -p "Reply with only: OK" --model "$MODEL" --output-format text &>/dev/null; then
    log "claude CLI authentication verified"
else
    error "claude CLI authentication failed. Run 'claude login' interactively."
    exit 1
fi

PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")

REPO_COUNT=$(python3 -c "import json; print(len(json.load(open('$REPOS_FILE'))))")
SUCCESS_COUNT=0

for i in $(seq 0 $((REPO_COUNT - 1))); do
    FULL_NAME=$(python3 -c "import json; print(json.load(open('$REPOS_FILE'))[$i]['full_name'])")
    OWNER=$(python3 -c "import json; print(json.load(open('$REPOS_FILE'))[$i]['owner'])")
    NAME=$(python3 -c "import json; print(json.load(open('$REPOS_FILE'))[$i]['name'])")
    DESCRIPTION=$(python3 -c "import json; print(json.load(open('$REPOS_FILE'))[$i].get('description', ''))")
    STARS=$(python3 -c "import json; print(json.load(open('$REPOS_FILE'))[$i].get('stars', 0))")
    LANGUAGE=$(python3 -c "import json; print(json.load(open('$REPOS_FILE'))[$i].get('language', ''))")
    TOPICS=$(python3 -c "import json; d=json.load(open('$REPOS_FILE'))[$i]; print(', '.join(d.get('topics', [])))")
    LICENSE=$(python3 -c "import json; print(json.load(open('$REPOS_FILE'))[$i].get('license', ''))")
    README=$(python3 -c "import json; print(json.load(open('$REPOS_FILE'))[$i].get('readme', ''))")

    # Safe filename: owner_repo
    SAFE_NAME="${OWNER}_${NAME}"
    OUTPUT_FILE="$ANALYSIS_DIR/${SAFE_NAME}.md"

    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        log "Analysis already exists: $OUTPUT_FILE"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        continue
    fi

    if [ -z "$README" ]; then
        error "No README for $FULL_NAME, skipping"
        continue
    fi

    log "Analyzing: $FULL_NAME ($STARS stars)"

    FULL_PROMPT="$PROMPT_TEMPLATE

---

## 레포지토리 정보
- **이름**: $FULL_NAME
- **URL**: https://github.com/$FULL_NAME
- **설명**: $DESCRIPTION
- **Stars**: $STARS
- **언어**: $LANGUAGE
- **토픽**: $TOPICS
- **라이선스**: $LICENSE

## README

$README"

    ATTEMPT=0
    ANALYSIS_OK=false

    while [ "$ATTEMPT" -le "$MAX_RETRIES" ]; do
        ATTEMPT=$((ATTEMPT + 1))

        if [ "$ATTEMPT" -gt 1 ]; then
            log "Retry $((ATTEMPT - 1))/$MAX_RETRIES for $FULL_NAME (previous output was not in Korean)"
            sleep 3
        fi

        if env -u CLAUDECODE claude -p "$FULL_PROMPT" --model "$MODEL" --output-format text > "$OUTPUT_FILE" 2>>"$LOG_FILE"; then
            strip_bkit_footer "$OUTPUT_FILE"

            if has_korean "$OUTPUT_FILE"; then
                ANALYSIS_OK=true
                break
            else
                error "Attempt $ATTEMPT: output for $FULL_NAME is not in Korean"
            fi
        else
            error "Attempt $ATTEMPT: claude CLI exited with error for $FULL_NAME"
            rm -f "$OUTPUT_FILE"
        fi
    done

    if [ "$ANALYSIS_OK" = true ]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        log "Analysis saved: $OUTPUT_FILE ($(wc -c < "$OUTPUT_FILE") bytes)"
    else
        error "All retries exhausted for $FULL_NAME — analysis failed"
        rm -f "$OUTPUT_FILE"
    fi

    sleep 2
done

if [ "$SUCCESS_COUNT" -eq 0 ]; then
    error "No repos were successfully analyzed"
    exit 1
fi

log "Analysis complete ($SUCCESS_COUNT/$REPO_COUNT repos)"
