#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULT_DIR="$ROOT_DIR/results/latest"
mkdir -p "$RESULT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "[run_all] python interpreter not found"
  exit 1
fi

TASKS=${TASKS:-120}
CONCURRENCY=${CONCURRENCY:-4}
PAYLOAD=${PAYLOAD:-256}
ITERS=${ITERS:-200}
SEED=${SEED:-42}

echo "[run_all] collecting env info"
"$ROOT_DIR/scripts/env_info.sh" > "$RESULT_DIR/env.txt"

echo "[run_all] python"
PYTHONPATH="$ROOT_DIR/python/src" "$PYTHON_BIN" -m runner \
  --workload cpu_hash \
  --mode single \
  --tasks "$TASKS" \
  --concurrency "$CONCURRENCY" \
  --payload "$PAYLOAD" \
  --iters "$ITERS" \
  --seed "$SEED" \
  --output "$RESULT_DIR/py_cpu_hash_single.json"

PYTHONPATH="$ROOT_DIR/python/src" "$PYTHON_BIN" -m runner \
  --workload cpu_hash \
  --mode process \
  --tasks "$TASKS" \
  --concurrency "$CONCURRENCY" \
  --payload "$PAYLOAD" \
  --iters "$ITERS" \
  --seed "$SEED" \
  --output "$RESULT_DIR/py_cpu_hash_process.json"

if command -v go >/dev/null 2>&1; then
  echo "[run_all] go"
  (cd "$ROOT_DIR/go" && go build -o "$RESULT_DIR/go_runner" ./cmd/runner)
  "$RESULT_DIR/go_runner" \
    --workload cpu_hash \
    --mode single \
    --tasks "$TASKS" \
    --concurrency "$CONCURRENCY" \
    --payload "$PAYLOAD" \
    --iters "$ITERS" \
    --seed "$SEED" \
    --output "$RESULT_DIR/go_cpu_hash_single.json"
  "$RESULT_DIR/go_runner" \
    --workload cpu_hash \
    --mode process \
    --tasks "$TASKS" \
    --concurrency "$CONCURRENCY" \
    --payload "$PAYLOAD" \
    --iters "$ITERS" \
    --seed "$SEED" \
    --output "$RESULT_DIR/go_cpu_hash_process.json"
else
  echo "[run_all] go not found, skipping"
fi

if command -v cargo >/dev/null 2>&1; then
  echo "[run_all] rust"
  (cd "$ROOT_DIR/rust" && cargo run --release -- \
    --workload cpu_hash \
    --mode single \
    --tasks "$TASKS" \
    --concurrency "$CONCURRENCY" \
    --payload "$PAYLOAD" \
    --iters "$ITERS" \
    --seed "$SEED" \
    --output "$RESULT_DIR/rs_cpu_hash_single.json")
  (cd "$ROOT_DIR/rust" && cargo run --release -- \
    --workload cpu_hash \
    --mode process \
    --tasks "$TASKS" \
    --concurrency "$CONCURRENCY" \
    --payload "$PAYLOAD" \
    --iters "$ITERS" \
    --seed "$SEED" \
    --output "$RESULT_DIR/rs_cpu_hash_process.json")
else
  echo "[run_all] cargo not found, skipping"
fi

echo "[run_all] summarize"
"$PYTHON_BIN" "$ROOT_DIR/scripts/summarize.py" --input "$RESULT_DIR" --output "$RESULT_DIR"

echo "[run_all] done -> $RESULT_DIR/summary.md"
