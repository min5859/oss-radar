#!/usr/bin/env bash
# OSS Radar - Weekly Open Source Discovery Pipeline
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/cron.log"

# Load secrets (GITHUB_TOKEN, etc.) from gitignored env file
if [ -f "$SCRIPT_DIR/config/.env" ]; then
    set -a
    source "$SCRIPT_DIR/config/.env"
    set +a
fi

# Activate venv if present (for cron environment)
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Ensure user-installed AI CLIs and optional Homebrew/nvm installs are visible.
# The nvm directory is optional on Linux; the newest globbed version ends up first.
for node_bin in "$HOME"/.nvm/versions/node/*/bin; do
    if [ -d "$node_bin" ]; then
        PATH="$node_bin:$PATH"
    fi
done
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:$PATH"

mkdir -p "$LOG_DIR" "$SCRIPT_DIR/data/analysis"

# Single log sink: route all stdout/stderr to the log file. launchd's StandardOutPath
# also points here, so a tee would write every line twice — echo to the redirected fd instead.
exec >> "$LOG_FILE" 2>&1

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [PIPELINE] $*"
}

error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $*"
}

START_TIME=$(date +%s)
log "========================================="
log "Starting weekly OSS Radar pipeline"
log "========================================="

# Step 1: Discover trending repos
log "Step 1/4: Discovering trending repos..."
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/discover.py" 2>>"$LOG_FILE"; then
    log "Step 1 complete"
else
    error "Step 1 failed: discover.py"
    exit 1
fi

# Step 2: Fetch README and metadata
log "Step 2/4: Fetching README and metadata..."
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/fetch.py" 2>>"$LOG_FILE"; then
    log "Step 2 complete"
else
    error "Step 2 failed: fetch.py"
    exit 1
fi

# Step 3: Analyze with AI CLI (partial failure allowed)
log "Step 3/4: Analyzing repos with AI CLI..."
STEP3_MARKER="$LOG_DIR/.step3-start"
: > "$STEP3_MARKER"
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/analyze.py" 2>>"$LOG_FILE"; then
    log "Step 3 complete"
else
    # Count only analysis files (re)generated during THIS run, not stale accumulated ones
    ANALYSIS_COUNT=$(find "$SCRIPT_DIR/data/analysis" -name "*.md" -size +0 -newer "$STEP3_MARKER" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$ANALYSIS_COUNT" -gt 0 ]; then
        log "Step 3 partially failed, but $ANALYSIS_COUNT fresh analysis file(s) from this run — continuing"
    else
        error "Step 3 failed: no fresh analysis files produced this run"
        exit 1
    fi
fi
rm -f "$STEP3_MARKER"

# Step 4: Publish to GitHub Wiki
PUBLISH_ARGS=()
if [ "${OSS_RADAR_DRY_RUN:-0}" = "1" ]; then
    PUBLISH_ARGS+=(--dry-run)
    log "Step 4/4: Validating GitHub Wiki output (dry-run)..."
else
    log "Step 4/4: Publishing to GitHub Wiki..."
fi
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/publish.py" "${PUBLISH_ARGS[@]}" 2>>"$LOG_FILE"; then
    log "Step 4 complete"
else
    error "Step 4 failed: publish.py"
    exit 1
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
log "========================================="
log "Pipeline complete in ${ELAPSED}s"
log "========================================="
