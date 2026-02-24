import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestPolyglotConcurrencyLab(unittest.TestCase):
    def test_python_runner_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "py.json"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "python" / "src")
            cmd = [
                sys.executable,
                "-m",
                "runner",
                "--workload",
                "cpu_hash",
                "--mode",
                "single",
                "--tasks",
                "8",
                "--concurrency",
                "2",
                "--payload",
                "64",
                "--iters",
                "20",
                "--seed",
                "42",
                "--output",
                str(output),
            ]
            completed = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["meta"]["language"], "python")
            self.assertEqual(data["meta"]["workload"], "cpu_hash")
            self.assertEqual(data["metrics"]["errors"]["count"], 0)

    def test_summarize_generates_md_and_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "in"
            output_dir = Path(tmpdir) / "out"
            input_dir.mkdir(parents=True, exist_ok=True)

            sample = {
                "meta": {
                    "language": "python",
                    "workload": "cpu_hash",
                    "mode": "single",
                    "tasks": 8,
                    "concurrency": 2,
                    "payload": 64,
                    "iters": 20,
                },
                "metrics": {
                    "wall_time_total_ms": 12.3,
                    "throughput_tasks_per_sec": 650.0,
                    "latency_ms": {"p50": 1.1, "p95": 2.2, "p99": 2.5},
                    "errors": {"count": 0},
                },
            }
            (input_dir / "sample.json").write_text(json.dumps(sample), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "summarize.py"),
                    "--input",
                    str(input_dir),
                    "--output",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output_dir / "summary.csv").exists())
            self.assertTrue((output_dir / "summary.md").exists())
            md_text = (output_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("Benchmark Summary", md_text)
            self.assertIn("cpu_hash", md_text)


if __name__ == "__main__":
    unittest.main()
