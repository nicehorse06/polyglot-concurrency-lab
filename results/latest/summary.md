# Benchmark Summary

| language | workload | mode | tasks | conc | wall(ms) | throughput(tasks/s) | p95(ms) | errors |
|---|---|---|---:|---:|---:|---:|---:|---:|
| python | cpu_hash | process | 20 | 2 | 0.624 | 32074.824 | 0.013 | 1 |
| python | cpu_hash | single | 20 | 2 | 0.29 | 69015.018 | 0.008 | 0 |
| python | cpu_hash | threads | 16 | 4 | 0.528 | 30305.441 | 0.005 | 0 |

## Quick Interpretation

- For `cpu_hash`, compare `single` vs `threads` vs `process` in each language.
- Python often improves on CPU-bound tasks with `process` instead of `threads` due to GIL.
- Go/Rust threads are usually closer to core-level scaling for this workload.