# Codex Prompt — Project Spec for `polyglot-concurrency-lab` (Read fully before coding)

You are helping build a teaching/demo GitHub repo: **polyglot-concurrency-lab**.  
The goal is to **demonstrate and compare performance** across **Go / Python / Rust** using the **same workload specifications**, showing:

- single execution (single-thread)
- multi-thread
- multi-process
- goroutines (Go)
- async (Python/Rust when appropriate)

This repo contains **no business logic**—it’s purely educational and benchmark-oriented.

---

## 0) Core Principles (must follow)
1. **Same workload spec across languages**: identical inputs and correctness checks.
2. **Reproducible**: fixed random seeds, fixed dataset sizes, print environment info (CPU/OS/versions).
3. **Teach the point**: highlight CPU-bound vs I/O-bound vs mixed workloads, and why different models win/lose.
4. **Minimal dependencies**: prefer standard libraries; only add popular deps when truly needed.
5. **Readable results**: output both machine-readable (JSON/CSV) and human-readable (Markdown tables).

---

## 1) Repo Layout (recommended)
polyglot-concurrency-lab/
  README.md
  LICENSE
  .gitignore
  workloads/
    spec.md                 # workload spec document (most important)
    datasets/               # optional fixed datasets (small enough to commit)
  results/
    latest/                 # latest run outputs (JSON/CSV/MD)
  scripts/
    run_all.sh              # one-command runner for all languages/modes
    summarize.py            # merges results -> generates reports/tables
    env_info.sh             # prints environment info (CPU/cores/OS/versions)
  go/
    cmd/
      runner/               # CLI entrypoint
    internal/
      workloads/
      runners/
      metrics/
    go.mod
  python/
    pyproject.toml
    src/
      runner/
      workloads/
      runners/
      metrics/
  rust/
    Cargo.toml
    src/
      main.rs               # CLI entrypoint
      workloads/
      runners/
      metrics/
  .github/workflows/
    bench.yml               # CI: small benchmark on GitHub runner (fast)

---

## 2) CLI Contract (must be consistent across languages)
Each language provides a runnable CLI with consistent options (names may vary slightly, semantics must match):

- --workload <name>            # cpu_hash / io_files / mixed_pipeline / fanout_fanin ...
- --mode <name>                # single / threads / process / goroutines / async
- --tasks <N>                  # number of tasks
- --concurrency <N>            # parallelism limit (threads/processes/goroutines/async max)
- --payload <size>             # per-task data size (bytes or iterations)
- --duration <sec> OR --iters <N>
- --warmup <sec> OR --warmup-iters <N>
- --output <path>              # JSON output path
- --seed <int>                 # deterministic randomness
- --verbose

Example commands (conceptual):
- Go:     ./go/bin/runner --workload cpu_hash --mode goroutines --tasks 20000 --concurrency 200 --iters 5 --output results/latest/go_cpu_hash.json
- Python: python -m runner --workload cpu_hash --mode process --tasks 20000 --concurrency 8 --iters 5 --output results/latest/py_cpu_hash.json
- Rust:   cargo run --release -- --workload cpu_hash --mode threads --tasks 20000 --concurrency 16 --iters 5 --output results/latest/rs_cpu_hash.json

---

## 3) Workloads (minimum 4; cover teaching goals)
`workloads/spec.md` must clearly define: **input**, **task behavior**, **correctness**, **tunable params**.

### W1: cpu_hash (CPU-bound)
- Each task: hash a fixed-size payload repeatedly (e.g., SHA256 for N rounds)
- Purpose: show Python GIL limits for CPU-bound threads; show process gains; show Go/Rust scaling
- Correctness: verify output checksum/prefix matches expected

### W2: io_files (I/O-bound)
- Each task: read/write/append or random-read files in a temp directory
- Purpose: show thread/async benefits for I/O; show process overhead tradeoffs
- Correctness: verify file content counts/checksums

### W3: mixed_pipeline (pipeline + mixed)
- Stages: I/O -> parse -> CPU transform -> aggregate
- Purpose: show bounded concurrency, backpressure, queue/channel patterns
- Correctness: aggregate result must match expected

### W4: fanout_fanin (scatter/gather + aggregation)
- Fanout: split a large job into N sub-tasks
- Fanin: collect and reduce results
- Purpose: demonstrate worker pools, join patterns, bounded queues
- Correctness: checksum or deterministic total sum

Optional “bonus” workloads:
- net_echo (local HTTP echo server + client load, highlights async/goroutine)
- sleep_jitter (huge task counts + short sleeps, shows scheduling/overhead)

---

## 4) Concurrency Modes (minimum support)
Each workload should run with the following modes (do as many as reasonable, but cover the core):

### Common modes
- single: sequential
- threads: multi-thread worker pool (bounded concurrency)
- process: multi-process worker pool (bounded concurrency)

### Go extras
- goroutines: goroutine + channel worker pool
- (optional) context cancellation + errgroup demo

### Python extras
- threads: threading or ThreadPoolExecutor
- process: multiprocessing or ProcessPoolExecutor
- async: asyncio + semaphore (when workload is I/O-suitable)

### Rust extras
- threads: std::thread + channels (or rayon if justified, document it)
- async: tokio + semaphore (when workload is I/O-suitable)
- (optional) crossbeam channels (if used, document why)

---

## 5) Metrics & Output Format (must be consistent)
Each run emits a JSON file with required fields:

- meta:
  - language: go|python|rust
  - version: version string
  - workload: name
  - mode: name
  - tasks, concurrency, payload, iters, warmup
  - timestamp
  - env: os, arch, cpu_model, cpu_cores, mem_total (as available)
- metrics:
  - wall_time_total_ms
  - throughput_tasks_per_sec
  - latency_ms: p50, p95, p99 (per-task latency)
  - cpu_time_ms (if available)
  - max_rss_mb (if available)
  - errors: count + sample messages

Nice-to-have language-specific metrics:
- context switches, goroutine count, queue depth, GC cycles

---

## 6) Unified Scripts & Reporting
`scripts/run_all.sh`:
- runs Go/Python/Rust
- executes a default matrix of workload + mode with small parameters (CI-friendly)
- outputs JSON to `results/latest/*.json`

`scripts/summarize.py`:
- reads `results/latest/*.json`
- writes `results/latest/summary.csv`
- writes `results/latest/summary.md` (Markdown table + short interpretation)
- (optional) updates a marked section in README with latest summary

---

## 7) README Minimum Content
1. What this repo compares and why
2. Workload overview (link to `workloads/spec.md`)
3. How to run (one-liners per language)
4. How to interpret results (expected differences for CPU vs I/O)
5. Common pitfalls:
   - Python GIL: CPU-bound threads won’t speed up
   - process has serialization/IPC overhead
   - goroutines are lightweight but not free (channels/locks/GC)
   - async mainly helps I/O-bound tasks
6. Environment caveats (local machine vs CI runner differs)

---

## 8) CI (GitHub Actions)
`.github/workflows/bench.yml`:
- on push/PR, run a **small** benchmark (avoid timeouts)
- run 1–2 parameter sets per workload
- upload `results/latest` as artifacts
- (optional) comment summary on PR

---

## 9) Suggested Implementation Order
Phase A: write specs + CLI + JSON output skeleton first  
Phase B: implement W1 cpu_hash with single/threads/process in all languages  
Phase C: implement W2 io_files (+ async/goroutines)  
Phase D: add W3/W4 to teach pipeline + fanout/fanin  
Phase E: reporting automation + README “latest results” section

---

## 10) Delivery Requirements (every change must preserve)
- Each language can run and produces JSON output
- Workloads are correct (checksum/aggregates verify)
- CLI semantics are consistent and documented
- Any third-party dependency must be justified in README

---

## Immediate Tasks for Codex (do now)
1) Create the repo skeleton and document scaffolding (README + workloads/spec.md)  
2) Implement W1 cpu_hash in all 3 languages: single/threads/process + JSON metrics  
3) Implement `scripts/run_all.sh` and `scripts/summarize.py` (generate summary.md table)  
4) Add a minimal `bench.yml` that runs only W1 with one small parameter set  

After completion, a user should be able to run:
- Go: go build / go run
- Python: uv/pip install + python -m runner
- Rust: cargo run --release
and get `results/latest/summary.md`.

(If there are language limitations, prioritize: correctness, consistent output, reproducibility.)