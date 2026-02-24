# polyglot-concurrency-lab

A teaching repo to compare concurrency behavior across **Go / Python / Rust** under the same workload contract.

Current implemented phase:

- Workload: `cpu_hash` (CPU-bound)
- Modes:
  - Python: `single`, `threads`, `process`, `async`
  - Go: `single`, `threads`, `process` (`goroutines` alias to thread worker pool)
  - Rust: `single`, `threads`, `process`
- Unified JSON metrics output for all languages
- Unified summarizer: CSV + Markdown report

## Why this repo

Interview prep often asks:

- Why Python threads may not speed up CPU-bound tasks (GIL)
- Why process pools can help CPU-bound workloads
- How Go goroutines and Rust threads differ in ergonomics and overhead
- How to compare throughput/latency fairly across languages

This repo gives deterministic, reproducible runs to answer those quickly.

## Workload Specs

See [workloads/spec.md](workloads/spec.md).

- `cpu_hash` is implemented.
- `io_files`, `mixed_pipeline`, `fanout_fanin` are scaffolded for next phase.

## Quick Start

### 1) Run all (recommended)

```bash
./scripts/run_all.sh
```

Outputs:

- `results/latest/*.json`
- `results/latest/summary.csv`
- `results/latest/summary.md`

### 2) Run each language manually

Python:

```bash
PYTHONPATH=python/src python -m runner \
  --workload cpu_hash --mode process --tasks 120 --concurrency 4 --payload 256 --iters 200 \
  --output results/latest/py_cpu_hash_process.json --seed 42
```

Go:

```bash
cd go
go run ./cmd/runner --workload cpu_hash --mode process --tasks 120 --concurrency 4 --payload 256 --iters 200 --output ../results/latest/go_cpu_hash_process.json --seed 42
```

Rust:

```bash
cd rust
cargo run --release -- --workload cpu_hash --mode process --tasks 120 --concurrency 4 --payload 256 --iters 200 --output ../results/latest/rs_cpu_hash_process.json --seed 42
```

## Output Schema

Each run writes JSON with:

- `meta`: language/version/workload/mode/tasks/concurrency/payload/iters/warmup/timestamp/env/seed
- `metrics`: wall time, throughput, latency p50/p95/p99, optional CPU/RSS, errors, checksum samples

## How to Interpret Results

- `cpu_hash` is CPU-bound:
  - Python: `process` typically outperforms `threads` for CPU-heavy tasks.
  - Go/Rust: threaded execution usually scales better with available cores.
- Use the same `tasks/payload/iters` when comparing languages.
- CI runner numbers and local machine numbers are expected to differ.

## Common Pitfalls

- Python GIL can limit CPU-bound thread speedups.
- Process mode has serialization and startup overhead.
- Goroutines are lightweight but still have scheduling/GC costs.
- Async is mainly useful for I/O-bound workloads, not pure CPU hashing.

## Repo Layout

- `workloads/spec.md`: workload contract and correctness rules
- `scripts/run_all.sh`: one-command benchmark launcher
- `scripts/summarize.py`: JSON -> CSV/Markdown summary
- `python/src/runner`: Python CLI runner
- `go/cmd/runner`: Go CLI runner
- `rust/src/main.rs`: Rust CLI runner
- `.github/workflows/bench.yml`: minimal CI benchmark

## Notes

- This phase intentionally uses minimal dependencies.
- Missing toolchains are skipped by `run_all.sh` with clear logs.
