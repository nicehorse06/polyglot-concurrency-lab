use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::env;
use std::fs;
use std::io;
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug)]
struct Config {
    workload: String,
    mode: String,
    tasks: usize,
    concurrency: usize,
    payload: usize,
    iters: usize,
    warmup_iters: usize,
    output: String,
    seed: u64,
    verbose: bool,
    worker: bool,
    worker_task_id: usize,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct Row {
    task_id: usize,
    digest_hex: String,
    latency_ms: f64,
}

fn parse_args() -> Config {
    let mut args: HashMap<String, String> = HashMap::new();
    let mut flags: Vec<String> = vec![];
    let raw: Vec<String> = env::args().collect();

    let mut i = 1;
    while i < raw.len() {
        if raw[i].starts_with("--") {
            if i + 1 < raw.len() && !raw[i + 1].starts_with("--") {
                args.insert(raw[i].clone(), raw[i + 1].clone());
                i += 2;
            } else {
                flags.push(raw[i].clone());
                i += 1;
            }
        } else {
            i += 1;
        }
    }

    Config {
        workload: args
            .get("--workload")
            .cloned()
            .unwrap_or_else(|| "cpu_hash".to_string()),
        mode: args
            .get("--mode")
            .cloned()
            .unwrap_or_else(|| "single".to_string()),
        tasks: args
            .get("--tasks")
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(100),
        concurrency: args
            .get("--concurrency")
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(4),
        payload: args
            .get("--payload")
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(256),
        iters: args
            .get("--iters")
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(100),
        warmup_iters: args
            .get("--warmup-iters")
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(0),
        output: args
            .get("--output")
            .cloned()
            .unwrap_or_else(|| "results/latest/rs_cpu_hash.json".to_string()),
        seed: args
            .get("--seed")
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(42),
        verbose: flags.contains(&"--verbose".to_string()),
        worker: flags.contains(&"--worker".to_string()),
        worker_task_id: args
            .get("--worker-task-id")
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(0),
    }
}

fn build_payload(seed: u64, task_id: usize, payload: usize) -> Vec<u8> {
    let base = format!("{}:{}:{}", seed, task_id, (seed + task_id as u64) % 1_000_000);
    let b = base.as_bytes();
    if payload <= b.len() {
        return b[..payload].to_vec();
    }

    let mut out = Vec::with_capacity(payload);
    while out.len() < payload {
        out.extend_from_slice(b);
    }
    out[..payload].to_vec()
}

fn cpu_hash_task(seed: u64, task_id: usize, payload: usize, iters: usize) -> Row {
    let mut data = build_payload(seed, task_id, payload);
    let started = Instant::now();
    for _ in 0..iters {
        let mut hasher = Sha256::new();
        hasher.update(&data);
        data = hasher.finalize().to_vec();
    }
    let latency_ms = started.elapsed().as_secs_f64() * 1000.0;
    Row {
        task_id,
        digest_hex: hex_string(&data),
        latency_ms,
    }
}

fn hex_string(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push_str(&format!("{:02x}", b));
    }
    s
}

fn run_single(cfg: &Config) -> Vec<Row> {
    (0..cfg.tasks)
        .map(|task_id| cpu_hash_task(cfg.seed, task_id, cfg.payload, cfg.iters))
        .collect()
}

fn run_threads(cfg: &Config) -> Vec<Row> {
    let workers = cfg.concurrency.max(1);
    let rows = Arc::new(Mutex::new(Vec::<Row>::with_capacity(cfg.tasks)));
    let next_job = Arc::new(Mutex::new(0usize));

    let mut handles = Vec::with_capacity(workers);
    for _ in 0..workers {
        let rows_ref = Arc::clone(&rows);
        let job_ref = Arc::clone(&next_job);
        let cfg_cloned = cfg.clone();
        handles.push(thread::spawn(move || {
            loop {
                let task_id_opt = {
                    let mut guard = job_ref.lock().expect("lock poisoned");
                    if *guard >= cfg_cloned.tasks {
                        None
                    } else {
                        let v = *guard;
                        *guard += 1;
                        Some(v)
                    }
                };

                let Some(task_id) = task_id_opt else {
                    break;
                };

                let row = cpu_hash_task(cfg_cloned.seed, task_id, cfg_cloned.payload, cfg_cloned.iters);
                rows_ref.lock().expect("lock poisoned").push(row);
            }
        }));
    }

    for h in handles {
        h.join().expect("thread failed");
    }

    Arc::try_unwrap(rows)
        .expect("rows still has references")
        .into_inner()
        .expect("rows lock poisoned")
}

fn run_process(cfg: &Config) -> io::Result<Vec<Row>> {
    let exe = env::current_exe()?;
    let workers = cfg.concurrency.max(1);
    let rows = Arc::new(Mutex::new(Vec::<Row>::with_capacity(cfg.tasks)));
    let next_job = Arc::new(Mutex::new(0usize));

    let mut handles = Vec::with_capacity(workers);
    for _ in 0..workers {
        let rows_ref = Arc::clone(&rows);
        let job_ref = Arc::clone(&next_job);
        let cfg_cloned = cfg.clone();
        let exe_cloned = exe.clone();

        handles.push(thread::spawn(move || -> io::Result<()> {
            loop {
                let task_id_opt = {
                    let mut guard = job_ref.lock().expect("lock poisoned");
                    if *guard >= cfg_cloned.tasks {
                        None
                    } else {
                        let v = *guard;
                        *guard += 1;
                        Some(v)
                    }
                };

                let Some(task_id) = task_id_opt else {
                    break;
                };

                let output = Command::new(&exe_cloned)
                    .arg("--worker")
                    .arg("--worker-task-id")
                    .arg(task_id.to_string())
                    .arg("--payload")
                    .arg(cfg_cloned.payload.to_string())
                    .arg("--iters")
                    .arg(cfg_cloned.iters.to_string())
                    .arg("--seed")
                    .arg(cfg_cloned.seed.to_string())
                    .output()?;

                if !output.status.success() {
                    return Err(io::Error::other("worker process failed"));
                }

                let row: Row = serde_json::from_slice(&output.stdout)
                    .map_err(|e| io::Error::other(e.to_string()))?;
                rows_ref.lock().expect("lock poisoned").push(row);
            }
            Ok(())
        }));
    }

    for h in handles {
        h.join().expect("thread failed")?;
    }

    Ok(
        Arc::try_unwrap(rows)
            .expect("rows still has references")
            .into_inner()
            .expect("rows lock poisoned"),
    )
}

fn percentile(values: &[f64], p: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let idx = ((p / 100.0) * ((sorted.len() - 1) as f64)).round() as usize;
    sorted[idx]
}

fn now_iso8601() -> String {
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    format!("{}", ts)
}

fn run(cfg: &Config) -> io::Result<serde_json::Value> {
    if cfg.workload != "cpu_hash" {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "only cpu_hash is implemented in this phase",
        ));
    }

    if cfg.warmup_iters > 0 {
        let warmup = Config {
            tasks: cfg.warmup_iters.min(cfg.tasks),
            ..cfg.clone()
        };
        let _ = run_single(&warmup);
    }

    let started = Instant::now();
    let mut rows = match cfg.mode.as_str() {
        "single" => run_single(cfg),
        "threads" => run_threads(cfg),
        "process" => run_process(cfg)?,
        _ => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("unsupported mode: {}", cfg.mode),
            ))
        }
    };
    let wall_ms = started.elapsed().as_secs_f64() * 1000.0;

    rows.sort_by_key(|r| r.task_id);
    let latencies: Vec<f64> = rows.iter().map(|r| r.latency_ms).collect();
    let checksum_sample: Vec<String> = rows
        .iter()
        .take(5)
        .map(|r| r.digest_hex.chars().take(16).collect())
        .collect();

    Ok(json!({
      "meta": {
        "language": "rust",
        "version": env!("CARGO_PKG_VERSION"),
        "workload": cfg.workload,
        "mode": cfg.mode,
        "tasks": cfg.tasks,
        "concurrency": cfg.concurrency,
        "payload": cfg.payload,
        "iters": cfg.iters,
        "warmup": cfg.warmup_iters,
        "timestamp": now_iso8601(),
        "seed": cfg.seed,
        "env": {
          "os": env::consts::OS,
          "arch": env::consts::ARCH,
          "cpu_model": "unknown",
          "cpu_cores": thread::available_parallelism().map(|n| n.get()).unwrap_or(1),
          "mem_total": "unknown"
        }
      },
      "metrics": {
        "wall_time_total_ms": round3(wall_ms),
        "throughput_tasks_per_sec": if wall_ms > 0.0 { round3(cfg.tasks as f64 / (wall_ms / 1000.0)) } else { 0.0 },
        "latency_ms": {
          "p50": round3(percentile(&latencies, 50.0)),
          "p95": round3(percentile(&latencies, 95.0)),
          "p99": round3(percentile(&latencies, 99.0)),
          "avg": round3(if latencies.is_empty() { 0.0 } else { latencies.iter().sum::<f64>() / latencies.len() as f64 })
        },
        "cpu_time_ms": serde_json::Value::Null,
        "max_rss_mb": serde_json::Value::Null,
        "errors": {
          "count": 0,
          "samples": []
        },
        "checksum_sample": checksum_sample
      }
    }))
}

fn round3(v: f64) -> f64 {
    (v * 1000.0).round() / 1000.0
}

fn ensure_parent(path: &str) -> io::Result<()> {
    if let Some(parent) = std::path::Path::new(path).parent() {
        fs::create_dir_all(parent)?;
    }
    Ok(())
}

fn main() -> io::Result<()> {
    let cfg = parse_args();

    if cfg.worker {
        let row = cpu_hash_task(cfg.seed, cfg.worker_task_id, cfg.payload, cfg.iters);
        println!("{}", serde_json::to_string(&row).map_err(|e| io::Error::other(e.to_string()))?);
        return Ok(());
    }

    let result = run(&cfg)?;
    ensure_parent(&cfg.output)?;
    fs::write(
        &cfg.output,
        serde_json::to_string_pretty(&result).map_err(|e| io::Error::other(e.to_string()))?,
    )?;

    if cfg.verbose {
        println!("{}", serde_json::to_string_pretty(&result).map_err(|e| io::Error::other(e.to_string()))?);
    } else {
        let wall = result["metrics"]["wall_time_total_ms"].as_f64().unwrap_or_default();
        let tps = result["metrics"]["throughput_tasks_per_sec"].as_f64().unwrap_or_default();
        println!("rust {}/{}: {:.3} ms, {:.3} tasks/s", cfg.workload, cfg.mode, wall, tps);
    }

    Ok(())
}
