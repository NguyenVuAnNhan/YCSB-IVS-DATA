# TOAST Hypothesis Trigger Analysis

Analyzed `YCSB-IVS-DATA/TOAST_HYPOTHESIS/HYPOTHESIS_DATA` against the latest hypotheses in `YCSB-IVS-DATA/insight`.

## Headline

The new high-resolution data keeps the root-cause verdict intact: JSONB/TOAST growth is the load-bearing mechanism. The sharper finding is about the immediate trigger: the recurring peaks are most consistent with a post-vacuum/cache-rewarming effect layered on top of large-value detoast and serialization cost, not with large-key sampling alone.

Detected main-run p95 peaks: `[49, 61, 73, 85, 96]` with spacings `[12, 12, 12, 11]`.

Main-run p95 rose from `260.9 us` in epochs 1-20 to `2,210.9 us` in epochs 91-100. Reference p95 stayed nearly flat.

## Phase Controls

| phase     | first 20 p95 us | last 10 p95 us | increase |
|-----------|-----------------|----------------|----------|
| run       | 260.9           | 2,210.9        | 8.48     |
| clean-run | 239.9           | 1,402.6        | 5.85     |
| avg-run   | 196.2           | 1,177.7        | 6.00     |
| reference | 61.2            | 64.4           | 1.05     |

The controls matter: `clean-run` and `avg-run` degrade, so large JSONB values alone hurt reads. The append-grown main `run` still ends worse than both controls, which preserves the physical-history/cache-locality part of the hypothesis.

## Peak Summary

| epoch | p95 us | prominence us | value p95 KiB | rows \>128 KiB % | sample key p95 KiB | slow rate % | vacuum s | run blks_read delta | mean IO waits |
|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| 49 | 946 | 117 | 73.0 | 1.62 | 78.7 | 4.47 | 196.4 | 16,775 | 0.000 |
| 61 | 1,335 | 283 | 90.8 | 2.79 | 95.0 | 8.29 | 327.2 | 23,368 | 0.130 |
| 73 | 1,928 | 557 | 107.6 | 3.52 | 122.9 | 12.79 | 380.3 | 40,829 | 0.116 |
| 85 | 2,619 | 1,191 | 125.6 | 4.84 | 134.3 | 16.99 | 540.2 | 52,376 | 0.212 |
| 96 | 3,769 | 2,002 | 141.8 | 6.19 | 143.7 | 20.94 | 653.1 | 80,095 | 0.250 |

## Trigger Tests

### Key Sampling

Large keys clearly create the expensive tail, but they do not fully explain the exact peak epochs. The top 5% sampled-latency reads in late epochs had a median key size of about `127.8 KiB`, while the rest of the late sample had a median near `62.9 KiB`; about `49.9%` of those top-tail reads were above `128 KiB`.

However, peak epochs did not consistently sample more large keys than their immediate neighbors. In several peaks, the sampled `>128 KiB` share or p99 key size is lower than the local non-peak mean. That makes key sampling a necessary ingredient, not the clock behind the 12-epoch rhythm.

### Cache Rewarming / Early-Run Penalty

The strongest trigger signal is intra-run front-loading. At every detected peak, the first quarter of the run has much worse sampled p95 latency and a much higher slow-read rate than quarters 2-4.

| epoch | sample q1 p95 us | sample q2-q4 mean p95 us | slow q1 rate % | slow q2-q4 rate % |
|---------------|---------------|---------------|---------------|---------------|
| 49 | 1,187 | 742 | 8.88 | 3.00 |
| 61 | 1,825 | 1,095 | 18.94 | 4.75 |
| 73 | 3,688 | 1,298 | 29.18 | 7.33 |
| 85 | 5,278 | 1,312 | 35.72 | 10.75 |
| 96 | 6,273 | 1,423 | 40.88 | 14.29 |

Run-phase `blks_read` deltas are also higher at the peaks than local neighbors, and `wait_io_count` rises modestly at later peaks. The direct buffer-residency test could not run because `pg_buffercache` was unavailable in this dataset, so the cache-residency part remains inferred rather than directly observed.

### Checkpoint / Writeback

Checkpoint and writeback pressure are supported as upstream pressure, not as the immediate peak trigger. The `extend` and `vacuum` phases accumulate large checkpoint/request/write deltas that grow with the TOAST relation. Inside the `run` phase, though, checkpoint write/sync deltas are usually zero at the detected peaks, and only epoch 49 has a requested checkpoint inside the run.

The OS disk sampler did not provide a usable disk-pressure signal: `0` run epochs had non-zero mean read/write/await values. That prevents a direct OS-level confirmation or rejection of writeback interference.

### Vacuum Perturbation

Vacuum remains a strong secondary contributor. Vacuum time grows with the workload and is locally elevated at most peaks, but not all of them. This fits a perturbation role: vacuum is part of the cycle that disturbs cache and writeback state before reads, while TOAST growth determines how expensive misses and detoast work become.

### Server vs Client Cost

The timing split points mostly to server-side query execution/detoast/serialization, with client JSON parsing as a meaningful amplifier. In epochs 80-100, slow reads spend about `63.1%` of mean latency in `query_execute_us` and `31.5%` in `json_parse_us`.

Late sampled latency by key-size bin:

| key size      | n      | p50 us | p95 us | query mean us | parse mean us |
|---------------|--------|--------|--------|---------------|---------------|
| \<=64 KiB     | 10,719 | 558    | 1,019  | 414           | 224           |
| 64-128 KiB    | 8,995  | 775    | 1,445  | 572           | 326           |
| 128-256 KiB   | 974    | 1,496  | 2,856  | 1,106         | 676           |
| 256-512 KiB   | 182    | 2,686  | 5,427  | 1,787         | 1,257         |
| 512 KiB-1 MiB | 25     | 7,334  | 9,695  | 3,295         | 3,195         |
| \>1 MiB       | 105    | 16,967 | 98,587 | 16,517        | 12,682        |

**Detoast Probe Split**

| epoch | probe | size KiB | lookup ms | serialize ms | serialize shared hits |
|-------|-------|----------|-----------|--------------|-----------------------|
| 1     | max   | 373.8    | 0.061     | 1.944        | 105                   |
| 1     | p95   | 2.6      | 0.043     | 0.121        | 32                    |
| 1     | p99   | 4.5      | 0.045     | 0.165        | 44                    |
| 50    | max   | 18,623.4 | 0.057     | 92.692       | 2,620                 |
| 50    | p95   | 74.5     | 0.052     | 0.800        | 84                    |
| 50    | p99   | 165.9    | 0.050     | 1.243        | 97                    |
| 100   | max   | 37,242.4 | 0.054     | 185.924      | 5,114                 |
| 100   | p95   | 147.6    | 0.047     | 1.105        | 96                    |
| 100   | p99   | 330.0    | 0.050     | 2.058        | 117                   |

## Local Peak Differences

This table compares each peak with non-peak epochs in its +/-2 epoch window.

| epoch | feature                    | peak       | local mean | peak minus local |
|-------|----------------------------|------------|------------|------------------|
| 49    | sample_pct_gt_128k         | 2.200      | 2.475      | -0.275           |
| 49    | slow_rate_pct              | 4.470      | 3.806      | 0.664            |
| 49    | duration_vacuum_s          | 196.425    | 194.010    | 2.415            |
| 49    | run_delta_blks_read        | 16,775.000 | 9,906.000  | 6,869.000        |
| 49    | run_wait_io_mean           | 0.000      | 0.048      | -0.048           |
| 49    | run_os_disk_read_kb_s_mean | 0.000      | 0.000      | 0.000            |
| 49    | run_os_disk_await_ms_mean  | 0.000      | 0.000      | 0.000            |
| 61    | sample_pct_gt_128k         | 2.400      | 2.775      | -0.375           |
| 61    | slow_rate_pct              | 8.293      | 6.445      | 1.848            |
| 61    | duration_vacuum_s          | 327.169    | 306.541    | 20.628           |
| 61    | run_delta_blks_read        | 23,368.000 | 11,943.750 | 11,424.250       |
| 61    | run_wait_io_mean           | 0.130      | 0.060      | 0.069            |
| 61    | run_os_disk_read_kb_s_mean | 0.000      | 0.000      | 0.000            |
| 61    | run_os_disk_await_ms_mean  | 0.000      | 0.000      | 0.000            |
| 73    | sample_pct_gt_128k         | 4.700      | 3.875      | 0.825            |
| 73    | slow_rate_pct              | 12.794     | 10.810     | 1.984            |
| 73    | duration_vacuum_s          | 380.257    | 419.805    | -39.548          |
| 73    | run_delta_blks_read        | 40,829.000 | 23,219.500 | 17,609.500       |
| 73    | run_wait_io_mean           | 0.116      | 0.073      | 0.043            |
| 73    | run_os_disk_read_kb_s_mean | 0.000      | 0.000      | 0.000            |
| 73    | run_os_disk_await_ms_mean  | 0.000      | 0.000      | 0.000            |
| 85    | sample_pct_gt_128k         | 5.600      | 5.100      | 0.500            |
| 85    | slow_rate_pct              | 16.995     | 15.224     | 1.771            |
| 85    | duration_vacuum_s          | 540.246    | 512.097    | 28.149           |
| 85    | run_delta_blks_read        | 52,376.000 | 36,773.500 | 15,602.500       |
| 85    | run_wait_io_mean           | 0.212      | 0.125      | 0.086            |
| 85    | run_os_disk_read_kb_s_mean | 0.000      | 0.000      | 0.000            |
| 85    | run_os_disk_await_ms_mean  | 0.000      | 0.000      | 0.000            |
| 96    | sample_pct_gt_128k         | 6.700      | 6.875      | -0.175           |
| 96    | slow_rate_pct              | 20.940     | 19.106     | 1.834            |
| 96    | duration_vacuum_s          | 653.103    | 598.766    | 54.337           |
| 96    | run_delta_blks_read        | 80,095.000 | 47,636.500 | 32,458.500       |
| 96    | run_wait_io_mean           | 0.250      | 0.133      | 0.117            |
| 96    | run_os_disk_read_kb_s_mean | 0.000      | 0.000      | 0.000            |
| 96    | run_os_disk_await_ms_mean  | 0.000      | 0.000      | 0.000            |

## Verdict

1.  TOAST/value-size amplification is confirmed again.
2.  Large-key sampling explains why the tail gets expensive, but not why peaks recur every roughly 12 epochs.
3.  The immediate trigger is most consistent with post-vacuum/cache rewarming: peak epochs are front-loaded, have higher slow-read rates, and have higher run-phase block-read deltas.
4.  Checkpoint/writeback pressure is probably an upstream amplifier, but the new run-phase counters and OS sampler do not show it as the direct peak event.
5.  Client parsing contributes, but server-side query execution/detoast/serialization dominates the slow-read split.

## Outputs

-   `epoch_summary.csv`
-   `peak_summary.csv`
-   `peak_window_comparison.csv`
-   `peak_quartile_profile.csv`
-   `key_size_latency_bins.csv`
-   `detoast_probe_summary.csv`
-   `toast_hypothesis_p95_peaks_slow_rate.png`
-   `toast_hypothesis_peak_quartile_latency.png`
-   `toast_hypothesis_late_latency_by_key_size.png`
-   `toast_hypothesis_run_read_pressure.png`