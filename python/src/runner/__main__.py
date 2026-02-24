import argparse
import asyncio
import hashlib
import json
import os
import platform
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def build_payload(seed: int, task_id: int, payload_size: int) -> bytes:
    random.seed(seed + task_id)
    base = f"{seed}:{task_id}:{random.randint(0, 1_000_000)}".encode("utf-8")
    if payload_size <= len(base):
        return base[:payload_size]
    repeats = (payload_size // len(base)) + 1
    return (base * repeats)[:payload_size]


def cpu_hash_task(args: Tuple[int, int, int, int]) -> Tuple[int, str, float]:
    seed, task_id, payload_size, rounds = args
    payload = build_payload(seed, task_id, payload_size)
    started = time.perf_counter()
    digest = payload
    for _ in range(rounds):
        digest = hashlib.sha256(digest).digest()
    latency_ms = (time.perf_counter() - started) * 1000
    return task_id, digest.hex(), latency_ms


def percentile(values: List[float], p: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(round((p / 100) * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def execute_single(tasks: int, seed: int, payload: int, rounds: int) -> List[Tuple[int, str, float]]:
    return [cpu_hash_task((seed, i, payload, rounds)) for i in range(tasks)]


def execute_threads(tasks: int, seed: int, payload: int, rounds: int, concurrency: int) -> List[Tuple[int, str, float]]:
    work = [(seed, i, payload, rounds) for i in range(tasks)]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(cpu_hash_task, work))


def execute_process(tasks: int, seed: int, payload: int, rounds: int, concurrency: int) -> List[Tuple[int, str, float]]:
    work = [(seed, i, payload, rounds) for i in range(tasks)]
    with ProcessPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(cpu_hash_task, work))


async def execute_async(tasks: int, seed: int, payload: int, rounds: int, concurrency: int) -> List[Tuple[int, str, float]]:
    sem = asyncio.Semaphore(concurrency)

    async def run_one(task_id: int) -> Tuple[int, str, float]:
        async with sem:
            return await asyncio.to_thread(cpu_hash_task, (seed, task_id, payload, rounds))

    coros = [run_one(i) for i in range(tasks)]
    return await asyncio.gather(*coros)


def collect_env() -> Dict[str, Any]:
    return {
        "os": platform.system(),
        "arch": platform.machine(),
        "cpu_model": platform.processor() or "unknown",
        "cpu_cores": os.cpu_count() or 1,
        "mem_total": "unknown",
        "python": platform.python_version(),
    }


def run(args: argparse.Namespace) -> Dict[str, Any]:
    if args.workload != "cpu_hash":
        raise ValueError("Only cpu_hash is implemented in this phase")

    if args.warmup_iters > 0:
        _ = execute_single(min(args.tasks, args.warmup_iters), args.seed, args.payload, args.iters)

    started = time.perf_counter()
    effective_mode = args.mode
    error_samples: List[str] = []
    if args.mode == "single":
        rows = execute_single(args.tasks, args.seed, args.payload, args.iters)
    elif args.mode == "threads":
        rows = execute_threads(args.tasks, args.seed, args.payload, args.iters, args.concurrency)
    elif args.mode == "process":
        try:
            rows = execute_process(args.tasks, args.seed, args.payload, args.iters, args.concurrency)
        except (PermissionError, OSError) as exc:
            # Some restricted environments deny semaphore/process creation.
            effective_mode = "threads"
            error_samples.append(f"process mode fallback to threads: {exc}")
            rows = execute_threads(args.tasks, args.seed, args.payload, args.iters, args.concurrency)
    elif args.mode == "async":
        rows = asyncio.run(execute_async(args.tasks, args.seed, args.payload, args.iters, args.concurrency))
    else:
        raise ValueError(f"Unsupported mode: {args.mode}")
    wall_ms = (time.perf_counter() - started) * 1000

    rows = sorted(rows, key=lambda x: x[0])
    latencies = [r[2] for r in rows]
    error_count = len(error_samples)

    result = {
        "meta": {
            "language": "python",
            "version": platform.python_version(),
            "workload": args.workload,
            "mode": args.mode,
            "mode_effective": effective_mode,
            "tasks": args.tasks,
            "concurrency": args.concurrency,
            "payload": args.payload,
            "iters": args.iters,
            "warmup": args.warmup_iters,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "env": collect_env(),
            "seed": args.seed,
        },
        "metrics": {
            "wall_time_total_ms": round(wall_ms, 3),
            "throughput_tasks_per_sec": round(args.tasks / (wall_ms / 1000), 3) if wall_ms else 0.0,
            "latency_ms": {
                "p50": round(percentile(latencies, 50), 3),
                "p95": round(percentile(latencies, 95), 3),
                "p99": round(percentile(latencies, 99), 3),
                "avg": round(statistics.mean(latencies), 3) if latencies else 0.0,
            },
            "cpu_time_ms": None,
            "max_rss_mb": None,
            "errors": {
                "count": error_count,
                "samples": error_samples,
            },
            "checksum_sample": [r[1][:16] for r in rows[:5]],
        },
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Python runner for polyglot concurrency lab")
    parser.add_argument("--workload", default="cpu_hash")
    parser.add_argument("--mode", default="single", choices=["single", "threads", "process", "async"])
    parser.add_argument("--tasks", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--payload", type=int, default=256)
    parser.add_argument("--duration", type=int, default=0)
    parser.add_argument("--iters", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--warmup-iters", type=int, default=0)
    parser.add_argument("--output", default="results/latest/py_cpu_hash.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.verbose:
        print(json.dumps(result, indent=2))
    else:
        m = result["metrics"]
        print(
            f"python {args.workload}/{args.mode}: {m['wall_time_total_ms']} ms, "
            f"{m['throughput_tasks_per_sec']} tasks/s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
