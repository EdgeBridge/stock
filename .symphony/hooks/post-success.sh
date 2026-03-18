#!/bin/bash
# Post-success hook: runs after successful agent completion.
# This is the QUALITY GATE — if this hook fails, PR must NOT be created.
set -e

echo "[symphony] Post-success validation for us-stock"

# --- venv verification ---
if [ ! -x "venv/bin/python" ]; then
    echo "[symphony] WARN: venv/bin/python not found — attempting recovery..."
    [ -L "venv" ] && rm -f venv

    SOURCE_VENV=""
    BASE_DIR=$(git worktree list --porcelain 2>/dev/null | head -1 | sed 's/^worktree //')
    if [ -n "$BASE_DIR" ] && [ -d "$BASE_DIR/venv" ]; then
        SOURCE_VENV="$BASE_DIR/venv"
    elif [ -d "/home/chans/us-stock/venv" ]; then
        SOURCE_VENV="/home/chans/us-stock/venv"
    fi

    if [ -z "$SOURCE_VENV" ]; then
        echo "[symphony] ERROR: Cannot locate venv — post-success gate FAILED"
        exit 1
    fi

    ln -s "$SOURCE_VENV" venv
    echo "[symphony] Recovered venv symlink -> $SOURCE_VENV"

    if [ ! -x "venv/bin/python" ]; then
        echo "[symphony] ERROR: venv/bin/python still not executable after recovery"
        exit 1
    fi
fi

echo "[symphony] Using Python: $(venv/bin/python --version)"

# --- Test suite gate ---
echo "[symphony] Running full test suite..."
venv/bin/python -m pytest backend/tests/ -x -q

# --- Test count gate ---
TEST_COUNT=$(venv/bin/python -m pytest backend/tests/ --co -q 2>/dev/null | tail -1 | grep -oP '^\d+')
if [ -z "$TEST_COUNT" ] || [ "$TEST_COUNT" -lt 1400 ]; then
    echo "[symphony] ERROR: Test count is ${TEST_COUNT:-0} (minimum: 1400)"
    exit 1
fi

# Lint is checked by CI gate, not here.
# This keeps the hook fast and avoids blocking on auto-fixable issues.

echo "[symphony] Post-success validation PASSED ($TEST_COUNT tests)"
