package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"math"
	"math/rand"
	"os"
	"os/exec"
	"runtime"
	"sort"
	"strconv"
	"sync"
	"time"
)

type config struct {
	Workload    string
	Mode        string
	Tasks       int
	Concurrency int
	Payload     int
	Iters       int
	WarmupIters int
	Output      string
	Seed        int
	Verbose     bool
	worker      bool
	workerTask  int
}

type row struct {
	TaskID    int
	DigestHex string
	LatencyMs float64
}

func buildPayload(seed, taskID, payloadSize int) []byte {
	r := rand.New(rand.NewSource(int64(seed + taskID)))
	base := []byte(fmt.Sprintf("%d:%d:%d", seed, taskID, r.Intn(1_000_000)))
	if payloadSize <= len(base) {
		return base[:payloadSize]
	}
	repeats := (payloadSize / len(base)) + 1
	payload := make([]byte, 0, payloadSize)
	for i := 0; i < repeats; i++ {
		payload = append(payload, base...)
	}
	return payload[:payloadSize]
}

func cpuHashTask(seed, taskID, payload, rounds int) row {
	data := buildPayload(seed, taskID, payload)
	start := time.Now()
	digest := data
	for i := 0; i < rounds; i++ {
		h := sha256.Sum256(digest)
		digest = h[:]
	}
	latency := float64(time.Since(start).Microseconds()) / 1000.0
	return row{TaskID: taskID, DigestHex: hex.EncodeToString(digest), LatencyMs: latency}
}

func runSingle(cfg config) []row {
	rows := make([]row, 0, cfg.Tasks)
	for i := 0; i < cfg.Tasks; i++ {
		rows = append(rows, cpuHashTask(cfg.Seed, i, cfg.Payload, cfg.Iters))
	}
	return rows
}

func runThreads(cfg config) []row {
	jobs := make(chan int, cfg.Tasks)
	results := make(chan row, cfg.Tasks)
	var wg sync.WaitGroup

	workers := cfg.Concurrency
	if workers < 1 {
		workers = 1
	}

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for taskID := range jobs {
				results <- cpuHashTask(cfg.Seed, taskID, cfg.Payload, cfg.Iters)
			}
		}()
	}

	for i := 0; i < cfg.Tasks; i++ {
		jobs <- i
	}
	close(jobs)
	wg.Wait()
	close(results)

	rows := make([]row, 0, cfg.Tasks)
	for r := range results {
		rows = append(rows, r)
	}
	return rows
}

func runProcess(cfg config) ([]row, error) {
	exe, err := os.Executable()
	if err != nil {
		return nil, err
	}

	sem := make(chan struct{}, maxInt(cfg.Concurrency, 1))
	results := make(chan row, cfg.Tasks)
	errCh := make(chan error, cfg.Tasks)
	var wg sync.WaitGroup

	for i := 0; i < cfg.Tasks; i++ {
		wg.Add(1)
		sem <- struct{}{}
		taskID := i
		go func() {
			defer wg.Done()
			defer func() { <-sem }()
			cmd := exec.Command(exe,
				"--worker",
				"--worker-task-id", strconv.Itoa(taskID),
				"--payload", strconv.Itoa(cfg.Payload),
				"--iters", strconv.Itoa(cfg.Iters),
				"--seed", strconv.Itoa(cfg.Seed),
			)
			out, runErr := cmd.Output()
			if runErr != nil {
				errCh <- runErr
				return
			}
			var r row
			if unmarshalErr := json.Unmarshal(out, &r); unmarshalErr != nil {
				errCh <- unmarshalErr
				return
			}
			results <- r
		}()
	}

	wg.Wait()
	close(results)
	close(errCh)

	if len(errCh) > 0 {
		return nil, <-errCh
	}

	rows := make([]row, 0, cfg.Tasks)
	for r := range results {
		rows = append(rows, r)
	}
	return rows, nil
}

func percentile(values []float64, p float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sorted := make([]float64, len(values))
	copy(sorted, values)
	sort.Float64s(sorted)
	idx := int(math.Round((p / 100.0) * float64(len(sorted)-1)))
	return sorted[idx]
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func mean(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	total := 0.0
	for _, v := range values {
		total += v
	}
	return total / float64(len(values))
}

func parseFlags() config {
	cfg := config{}
	flag.StringVar(&cfg.Workload, "workload", "cpu_hash", "workload name")
	flag.StringVar(&cfg.Mode, "mode", "single", "single|threads|process|goroutines")
	flag.IntVar(&cfg.Tasks, "tasks", 100, "number of tasks")
	flag.IntVar(&cfg.Concurrency, "concurrency", 4, "concurrency limit")
	flag.IntVar(&cfg.Payload, "payload", 256, "payload size")
	flag.IntVar(&cfg.Iters, "iters", 100, "hash rounds")
	flag.IntVar(&cfg.WarmupIters, "warmup-iters", 0, "warmup task count")
	flag.StringVar(&cfg.Output, "output", "results/latest/go_cpu_hash.json", "output path")
	flag.IntVar(&cfg.Seed, "seed", 42, "random seed")
	flag.BoolVar(&cfg.Verbose, "verbose", false, "verbose output")
	flag.BoolVar(&cfg.worker, "worker", false, "internal worker mode")
	flag.IntVar(&cfg.workerTask, "worker-task-id", 0, "internal worker task id")
	flag.Parse()
	if cfg.Mode == "goroutines" {
		cfg.Mode = "threads"
	}
	return cfg
}

func run(cfg config) (map[string]any, error) {
	if cfg.Workload != "cpu_hash" {
		return nil, errors.New("only cpu_hash is implemented in this phase")
	}

	if cfg.WarmupIters > 0 {
		warmup := cfg
		warmup.Tasks = minInt(cfg.WarmupIters, cfg.Tasks)
		_ = runSingle(warmup)
	}

	start := time.Now()
	var rows []row
	var err error

	switch cfg.Mode {
	case "single":
		rows = runSingle(cfg)
	case "threads":
		rows = runThreads(cfg)
	case "process":
		rows, err = runProcess(cfg)
	default:
		return nil, fmt.Errorf("unsupported mode: %s", cfg.Mode)
	}
	if err != nil {
		return nil, err
	}

	wallMs := float64(time.Since(start).Microseconds()) / 1000.0
	sort.Slice(rows, func(i, j int) bool { return rows[i].TaskID < rows[j].TaskID })

	latencies := make([]float64, 0, len(rows))
	checksumSample := make([]string, 0, 5)
	for idx, r := range rows {
		latencies = append(latencies, r.LatencyMs)
		if idx < 5 {
			if len(r.DigestHex) > 16 {
				checksumSample = append(checksumSample, r.DigestHex[:16])
			} else {
				checksumSample = append(checksumSample, r.DigestHex)
			}
		}
	}

	result := map[string]any{
		"meta": map[string]any{
			"language":    "go",
			"version":     runtime.Version(),
			"workload":    cfg.Workload,
			"mode":        cfg.Mode,
			"tasks":       cfg.Tasks,
			"concurrency": cfg.Concurrency,
			"payload":     cfg.Payload,
			"iters":       cfg.Iters,
			"warmup":      cfg.WarmupIters,
			"timestamp":   time.Now().UTC().Format(time.RFC3339),
			"seed":        cfg.Seed,
			"env": map[string]any{
				"os":        runtime.GOOS,
				"arch":      runtime.GOARCH,
				"cpu_model": "unknown",
				"cpu_cores": runtime.NumCPU(),
				"mem_total": "unknown",
			},
		},
		"metrics": map[string]any{
			"wall_time_total_ms":       round3(wallMs),
			"throughput_tasks_per_sec": round3(float64(cfg.Tasks) / (wallMs / 1000.0)),
			"latency_ms": map[string]any{
				"p50": round3(percentile(latencies, 50)),
				"p95": round3(percentile(latencies, 95)),
				"p99": round3(percentile(latencies, 99)),
				"avg": round3(mean(latencies)),
			},
			"cpu_time_ms": nil,
			"max_rss_mb":  nil,
			"errors": map[string]any{
				"count":   0,
				"samples": []string{},
			},
			"checksum_sample": checksumSample,
		},
	}
	return result, nil
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func round3(v float64) float64 {
	return math.Round(v*1000) / 1000
}

func main() {
	cfg := parseFlags()

	if cfg.worker {
		r := cpuHashTask(cfg.Seed, cfg.workerTask, cfg.Payload, cfg.Iters)
		encoded, _ := json.Marshal(r)
		fmt.Println(string(encoded))
		return
	}

	result, err := run(cfg)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	encoded, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	if err := os.MkdirAll(dirName(cfg.Output), 0o755); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := os.WriteFile(cfg.Output, encoded, 0o644); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	if cfg.Verbose {
		fmt.Println(string(encoded))
	} else {
		metrics := result["metrics"].(map[string]any)
		fmt.Printf("go %s/%s: %.3f ms, %.3f tasks/s\n", cfg.Workload, cfg.Mode, metrics["wall_time_total_ms"], metrics["throughput_tasks_per_sec"])
	}
}

func dirName(path string) string {
	for i := len(path) - 1; i >= 0; i-- {
		if path[i] == '/' {
			if i == 0 {
				return "/"
			}
			return path[:i]
		}
	}
	return "."
}
