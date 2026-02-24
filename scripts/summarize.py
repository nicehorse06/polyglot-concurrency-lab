import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def load_rows(input_dir: Path) -> List[Dict]:
    rows: List[Dict] = []
    for path in sorted(input_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("meta", {})
        metrics = data.get("metrics", {})
        lat = metrics.get("latency_ms", {})
        rows.append(
            {
                "file": path.name,
                "language": meta.get("language", "unknown"),
                "workload": meta.get("workload", "unknown"),
                "mode": meta.get("mode", "unknown"),
                "tasks": meta.get("tasks", 0),
                "concurrency": meta.get("concurrency", 0),
                "payload": meta.get("payload", 0),
                "iters": meta.get("iters", 0),
                "wall_time_total_ms": metrics.get("wall_time_total_ms", 0),
                "throughput_tasks_per_sec": metrics.get("throughput_tasks_per_sec", 0),
                "latency_p50_ms": lat.get("p50", 0),
                "latency_p95_ms": lat.get("p95", 0),
                "latency_p99_ms": lat.get("p99", 0),
                "error_count": metrics.get("errors", {}).get("count", 0),
            }
        )
    return rows


def write_csv(rows: List[Dict], output_csv: Path) -> None:
    fields = [
        "file",
        "language",
        "workload",
        "mode",
        "tasks",
        "concurrency",
        "payload",
        "iters",
        "wall_time_total_ms",
        "throughput_tasks_per_sec",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "error_count",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_md(rows: List[Dict], output_md: Path) -> None:
    lines = [
        "# Benchmark Summary",
        "",
        "| language | workload | mode | tasks | conc | wall(ms) | throughput(tasks/s) | p95(ms) | errors |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    sorted_rows = sorted(rows, key=lambda r: (r["workload"], r["language"], r["mode"]))
    for r in sorted_rows:
        lines.append(
            "| {language} | {workload} | {mode} | {tasks} | {concurrency} | {wall_time_total_ms} | {throughput_tasks_per_sec} | {latency_p95_ms} | {error_count} |".format(
                **r
            )
        )

    lines.extend(
        [
            "",
            "## Quick Interpretation",
            "",
            "- For `cpu_hash`, compare `single` vs `threads` vs `process` in each language.",
            "- Python often improves on CPU-bound tasks with `process` instead of `threads` due to GIL.",
            "- Go/Rust threads are usually closer to core-level scaling for this workload.",
        ]
    )
    output_md.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize benchmark JSON outputs")
    parser.add_argument("--input", default="results/latest", help="directory containing JSON results")
    parser.add_argument("--output", default="results/latest", help="directory to write summary files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(input_dir)
    write_csv(rows, output_dir / "summary.csv")
    write_md(rows, output_dir / "summary.md")

    print(f"summarized {len(rows)} files -> {output_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
