#!/usr/bin/env bash
set -uo pipefail

echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "os=$(uname -s)"
echo "arch=$(uname -m)"
if command -v nproc >/dev/null 2>&1; then
  echo "cpu_cores=$(nproc)"
elif command -v sysctl >/dev/null 2>&1; then
  cores="$(sysctl -n hw.logicalcpu 2>/dev/null || true)"
  if [[ -n "$cores" ]]; then
    echo "cpu_cores=$cores"
  else
    echo "cpu_cores=unknown"
  fi
else
  echo "cpu_cores=unknown"
fi
if command -v python3 >/dev/null 2>&1; then
  echo "python=$(python3 --version 2>&1)"
elif command -v python >/dev/null 2>&1; then
  echo "python=$(python --version 2>&1)"
fi
if command -v go >/dev/null 2>&1; then
  echo "go=$(go version 2>&1)"
fi
if command -v cargo >/dev/null 2>&1; then
  echo "rust=$(rustc --version 2>&1)"
fi
