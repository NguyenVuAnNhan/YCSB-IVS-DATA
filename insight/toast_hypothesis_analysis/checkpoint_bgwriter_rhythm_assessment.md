# Checkpoint / Bgwriter Rhythm Assessment

Assessed existing `checkpoint_observations.csv` and `pg_1s.csv` against main-run p95 peaks.

## Bottom Line

The data does **not** support checkpoint/bgwriter as the direct clock for the p95 spikes. It supports checkpoint/bgwriter as background pressure that grows with TOAST size, but the clean 12-ish p95 rhythm is not mirrored by checkpoint events or write-time deltas.

Detected p95 peak epochs: `[49, 61, 73, 85, 96]`.

## Peak Epochs

| epoch | p95 us | prominence us |
| --- | --- | --- |
| 49 | 946 | 117 |
| 61 | 1,335 | 283 |
| 73 | 1,928 | 557 |
| 85 | 2,619 | 1,191 |
| 96 | 3,769 | 2,002 |

## Direct Run-Phase Checkpoint Evidence

At the p95 peaks, run-phase checkpoint write/sync deltas are almost entirely absent. Non-zero run-phase checkpoint counters at p95 peaks:

| Epoch | run_delta_checkpoints_timed | run_delta_checkpoints_req | run_delta_checkpoint_write_time | run_delta_checkpoint_sync_time |
| --- | --- | --- | --- | --- |
| 49 | 0 | 1 | 0 | 0 |

This weakens the idea that a checkpoint event inside the read phase directly causes the spike.

## Local Peak Comparison

Compared each p95 peak to non-peak epochs in its +/-2 epoch window:

| peak epoch | feature | peak | local mean | peak minus local |
| --- | --- | --- | --- | --- |
| 49 | extend_delta_checkpoints_req | 35 | 36 | -1 |
| 49 | extend_delta_checkpoint_write_time | 474,183 | 462,424 | 11,759 |
| 49 | vacuum_delta_checkpoints_req | 1 | 1 | -0 |
| 49 | vacuum_delta_checkpoint_write_time | 197,198 | 116,168 | 81,030 |
| 49 | run_delta_checkpoints_req | 1 | 0 | 1 |
| 49 | run_delta_checkpoint_write_time | 0 | 0 | 0 |
| 49 | run_delta_buffers_checkpoint | 78,453 | 9,873 | 68,580 |
| 49 | run_delta_buffers_backend | 2,187 | 602 | 1,584 |
| 61 | extend_delta_checkpoints_req | 45 | 46 | -0 |
| 61 | extend_delta_checkpoint_write_time | 603,185 | 608,460 | -5,274 |
| 61 | vacuum_delta_checkpoints_req | 2 | 2 | 0 |
| 61 | vacuum_delta_checkpoint_write_time | 162,596 | 190,205 | -27,609 |
| 61 | run_delta_checkpoints_req | 0 | 0 | 0 |
| 61 | run_delta_checkpoint_write_time | 0 | 84,140 | -84,140 |
| 61 | run_delta_buffers_checkpoint | 6,198 | 21,963 | -15,765 |
| 61 | run_delta_buffers_backend | 0 | 1,778 | -1,778 |
| 73 | extend_delta_checkpoints_req | 55 | 56 | -0 |
| 73 | extend_delta_checkpoint_write_time | 619,850 | 663,416 | -43,566 |
| 73 | vacuum_delta_checkpoints_req | 2 | 2 | 0 |
| 73 | vacuum_delta_checkpoint_write_time | 221,184 | 382,816 | -161,632 |
| 73 | run_delta_checkpoints_req | 0 | 0 | 0 |
| 73 | run_delta_checkpoint_write_time | 0 | 0 | 0 |
| 73 | run_delta_buffers_checkpoint | 85,008 | 48,554 | 36,454 |
| 73 | run_delta_buffers_backend | 108 | 0 | 108 |
| 85 | extend_delta_checkpoints_req | 66 | 66 | 0 |
| 85 | extend_delta_checkpoint_write_time | 875,970 | 854,802 | 21,168 |
| 85 | vacuum_delta_checkpoints_req | 2 | 2 | -0 |
| 85 | vacuum_delta_checkpoint_write_time | 436,165 | 413,649 | 22,516 |
| 85 | run_delta_checkpoints_req | 0 | 0 | 0 |
| 85 | run_delta_checkpoint_write_time | 0 | 55,757 | -55,757 |
| 85 | run_delta_buffers_checkpoint | 12,603 | 21,741 | -9,138 |
| 85 | run_delta_buffers_backend | 723 | 1,902 | -1,178 |
| 96 | extend_delta_checkpoints_req | 75 | 75 | -0 |
| 96 | extend_delta_checkpoint_write_time | 990,507 | 921,962 | 68,545 |
| 96 | vacuum_delta_checkpoints_req | 3 | 2 | 2 |
| 96 | vacuum_delta_checkpoint_write_time | 478,759 | 522,555 | -43,796 |
| 96 | run_delta_checkpoints_req | 0 | 0 | 0 |
| 96 | run_delta_checkpoint_write_time | 0 | 67,391 | -67,391 |
| 96 | run_delta_buffers_checkpoint | 8,600 | 46,408 | -37,808 |
| 96 | run_delta_buffers_backend | 13,503 | 10,809 | 2,694 |

The local comparison is mixed. Extend/vacuum checkpoint request and write-time counters usually grow with epoch, but they do not consistently jump at the exact p95 peaks. Some run-phase buffer counters do jump locally, especially `run_delta_buffers_checkpoint`/`run_delta_buffers_backend`, but that is more consistent with shared-buffer/cache pressure during the read phase than checkpoint timing as a clean metronome.

## Lagged Correlations

Positive lag means the metric from earlier epochs is compared to current p95.

| feature | metric lag epochs | Spearman vs p95 |
| --- | --- | --- |
| cycle_delta_checkpoints_req | -3 | 0.987 |
| cycle_delta_wal_bytes | -2 | 0.986 |
| extend_delta_wal_bytes | -2 | 0.986 |
| extend_delta_checkpoints_req | -3 | 0.986 |
| cycle_delta_checkpoints_req | -2 | 0.986 |
| extend_delta_wal_bytes | -3 | 0.986 |
| cycle_delta_wal_bytes | -3 | 0.986 |
| cycle_delta_wal_bytes | -4 | 0.986 |
| cycle_delta_checkpoints_req | -4 | 0.986 |
| extend_delta_checkpoints_req | -2 | 0.986 |
| extend_delta_wal_bytes | -4 | 0.986 |
| extend_delta_checkpoints_req | -4 | 0.986 |

These high correlations should be read cautiously because many checkpoint/bgwriter counters trend upward with TOAST growth. They do not by themselves establish a periodic trigger.

## 12-Epoch Rhythm Test

Residual autocorrelation after subtracting a 9-epoch rolling median trend, evaluated at lag 12:

| feature | lag-12 residual autocorr |
| --- | --- |
| p95_us | 0.356 |
| cycle_delta_checkpoint_write_time | 0.316 |
| vacuum_delta_checkpoint_write_time | 0.079 |
| extend_delta_checkpoint_write_time | 0.077 |
| cycle_delta_checkpoints_req | 0.031 |
| extend_delta_checkpoints_req | 0.014 |
| run_delta_buffers_backend | -0.088 |
| vacuum_delta_checkpoints_req | -0.099 |
| run_delta_buffers_checkpoint | -0.129 |
| cycle_delta_buffers_checkpoint | -0.238 |

The p95 residual has a 12-epoch component, but checkpoint/bgwriter residuals do not show a matching, strong, consistent lag-12 signature.

## Interpretation

- Checkpoint/bgwriter pressure is real and grows with the workload.
- It probably contributes to dirty-buffer churn and shared-buffer turnover after extend/vacuum.
- But with the current data, the p95 spike clock is better supported by variable shared-buffer miss pressure during the subsequent run (`blks_read`, early-run slow-read rate) than by direct checkpoint/writeback events.
- To prove checkpoint/bgwriter as a trigger, we would need checkpoint logs or non-zero OS writeback/disk counters aligning in time with the early-run slow-read bursts.

## Outputs

- `checkpoint_bgwriter_epoch_summary.csv`
- `checkpoint_bgwriter_phase_deltas.csv`
- `checkpoint_bgwriter_peak_local_comparison.csv`
- `checkpoint_bgwriter_interesting_peak_comparison.csv`
- `checkpoint_bgwriter_lag_correlations.csv`
- `checkpoint_bgwriter_residual_autocorrelation.csv`
- `checkpoint_bgwriter_vs_p95.png`
- `checkpoint_bgwriter_residual_autocorrelation.png`
