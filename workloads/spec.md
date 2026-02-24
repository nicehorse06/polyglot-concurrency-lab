# Workload Specification

This file defines deterministic benchmark workloads shared across Go / Python / Rust.

## Common Inputs

- `tasks`: number of independent tasks
- `concurrency`: max in-flight workers
- `payload`: bytes per task payload
- `iters`: inner loop rounds
- `seed`: deterministic seed

## W1: `cpu_hash` (implemented)

- Input: payload bytes generated from `seed + task_id`
- Behavior: run SHA256 repeatedly for `iters` rounds
- Correctness:
  - each task output must be deterministic
  - same language+config should produce stable digest samples across runs
- Teaching goal:
  - CPU-bound work favors process-based parallelism in Python
  - Go/Rust threads/goroutines can scale with cores

## W2: `io_files` (scaffold)

- Input: deterministic temp file operations
- Behavior: read/write/append fixed chunks
- Correctness: total bytes and checksums must match expected
- Teaching goal: compare threads/async for I/O-bound tasks

## W3: `mixed_pipeline` (scaffold)

- Input: records flow through staged pipeline
- Behavior: I/O read -> parse -> CPU transform -> aggregate
- Correctness: final aggregate checksum/total must match expected
- Teaching goal: bounded queues/channels and backpressure

## W4: `fanout_fanin` (scaffold)

- Input: one large deterministic job split into chunks
- Behavior: scatter work to workers, then reduce results
- Correctness: deterministic final sum/checksum
- Teaching goal: worker pools + join/reduction patterns
