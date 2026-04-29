# JSON Blue Evidence for JSONB TOAST Amplification

Generated from the current `JSON_BLUE` latency CSVs and the available run 4-6 value-size matrices.

## What The Current Data Supports

- The anomalous late main-run READ p95 increase is replicated across all four JSON Blue runs.
  The late-window main-run p95 mean is 3.3x to 9.7x the first-20-epoch mean.
- The unchanged `reference` read control remains near-flat at about 52 us late-window p95, while the main run averages about 1401 us.
- `clean-run` and `avg-run` also rise late (735 us and 617 us p95 on average), which says larger values alone matter. The main run is still higher, which is consistent with additional storage/history effects from the append-grown table.
- At a 1000 us p95 threshold, the late high-latency regions include: run 3 epochs 69-74 (6 epochs); run 3 epochs 79-89 (11 epochs); run 3 epochs 93-100 (8 epochs); run 4 epochs 80-87 (8 epochs); run 4 epochs 93-100 (8 epochs); run 5 epochs 82-87 (6 epochs); run 5 epochs 92-100 (9 epochs); run 6 epochs 79-90 (12 epochs); run 6 epochs 94-100 (7 epochs). This matches the observation that the main-run spikes are clustered in roughly multi-epoch windows rather than one isolated point.

## Evidence Linking The Spike To Large Toasted Values

- In the value-size matrices for runs 4-6, mean p99 logical row size grows from about 4.4 KiB at epoch 1 to about 330.1 KiB at epoch 100.
- Using PostgreSQL's roughly 2 KiB TOAST chunk scale as an estimate, that is about 3 chunks at epoch 1 versus about 170 chunks at epoch 100 for the p99 row.
- By epoch 60, about 98.0% of rows in the available value-size matrices are already above 32 KiB logical size. That means p95 reads are no longer rare single-tuple reads; many reads are eligible to fetch and detoast large varlena payloads.

## Internal PostgreSQL Proxy Evidence

The original dataset does not contain direct TOAST table sizes or detoast timings, so these are proxies rather than proof. Still, main-run p95 tracks PostgreSQL counter deltas strongly:

| feature | spearman_rho | n |
| --- | --- | --- |
| AverageLatency(us) | 0.964 | 400 |
| value_size_p95 | 0.906 | 300 |
| est_toast_chunks_p95 | 0.905 | 300 |
| est_toast_chunks_p99 | 0.903 | 300 |
| value_size_p99 | 0.902 | 300 |
| value_size_max | 0.902 | 300 |
| est_toast_chunks_max | 0.902 | 300 |
| buffers_alloc_per_op_delta | 0.901 | 400 |

Interpretation: latency rises with buffer allocation, tuple-return/fetch pressure, WAL/checkpoint-related deltas, and estimated TOAST fanout. That is the expected shape if large JSONB array values are increasing the amount of PostgreSQL work needed for a read path.

## Plots

- `json_blue_toast_evidence/01_main_run_p95_spike_windows.png`
- `json_blue_toast_evidence/02_phase_control_p95_mean.png`
- `json_blue_toast_evidence/03_main_run_excess_vs_clean_control.png`
- `json_blue_toast_evidence/04_tail_value_size_and_estimated_toast_chunks.png`
- `json_blue_toast_evidence/05_latency_vs_estimated_toast_chunks.png`
- `json_blue_toast_evidence/06_internal_proxy_correlations.png`
- `json_blue_toast_evidence/07_run_phase_internal_proxies.png`
- `json_blue_toast_evidence/08_watcher_proc_io_vs_p95_diagnostic.png`
- `json_blue_toast_evidence/09_watcher_cpu_memory_vs_p95.png`

## Watcher Metrics Check

The stored watcher `.metrics` files for runs 4-6 do include per-second CPU and memory samples for the main `run` phase. They do not include useful process I/O deltas: every stored `delta_read` and `delta_write` value is zero across the available run/phase watcher files.

That means the current watcher files cannot directly test a visual `delta_read`/`delta_write` spike. The best current spike-parallel signals remain the PostgreSQL counter deltas in the main CSVs (`blks_read`, `buffers_alloc`, WAL records/bytes) and the value-size/estimated-TOAST fanout summaries.

Watcher CPU/memory correlations with p95 are saved in `watcher_metric_correlations.csv`; they are weaker and less mechanism-specific than the PostgreSQL counter proxies.

## Limits

- Runs 4-6 have full value-size matrices for this scenario; run 3 contributes to latency evidence but not tail-size plots.
- The current CSV counters are cumulative PostgreSQL statistics sampled after phases. The per-op deltas are useful support, but they are not as clean as the new one-shot `.dbstats` and detoast probes we added to the harness.
- The TOAST chunk counts here are estimates from logical value size. The confirmation run should use direct TOAST relation size/chunk instrumentation and detoast probes.

Bottom line: the current dataset already supports the JSONB TOAST amplification hypothesis. It does not prove the internal mechanism by itself, but the timing, controls, value-size tail growth, and PostgreSQL counter proxies all point in the same direction.
