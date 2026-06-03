#!/usr/bin/env bash
# local_updater.sh — 로컬에서 NEC 데이터를 주기적으로 fetch하여 GitHub에 push
# 사용법: ./scripts/local_updater.sh [간격(초, 기본값=90)]
# 종료:   Ctrl+C

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INTERVAL="${1:-90}"   # 기본 90초(1분 30초)

LATEST_JSON="public/data/latest.json"
HISTORY_JSON="public/data/history.json"

cd "$REPO_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "=== NEC 로컬 자동 업데이터 시작 ==="
log "저장소: $REPO_DIR"
log "업데이트 간격: ${INTERVAL}초"
log "종료하려면 Ctrl+C 를 누르세요."
echo ""

run_once() {
    log "--- NEC 데이터 수집 시작 ---"

    if python3 "$SCRIPT_DIR/fetch_nec.py" \
        --output "$LATEST_JSON" \
        --history "$HISTORY_JSON"; then
        log "데이터 수집 완료"
    else
        log "⚠️  데이터 수집 실패 — 이전 데이터 유지, 다음 주기에 재시도"
        return
    fi

    # 변경사항 확인
    git add "$LATEST_JSON" "$HISTORY_JSON"
    if git diff --cached --quiet; then
        log "변경된 데이터 없음 — push 생략"
        return
    fi

    TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S KST')"
    git commit -m "chore: update NEC data at ${TIMESTAMP}"
    git push origin main
    log "✅ GitHub push 완료"
}

# 첫 실행은 즉시
run_once

# 이후 INTERVAL초마다 반복
while true; do
    log "다음 실행까지 ${INTERVAL}초 대기..."
    sleep "$INTERVAL"
    run_once
done
