# Wide CSV Feature Ridge Model for Main-Run p95

This model uses a much wider set of predictors from the CSV/dbstats data while excluding direct latency-sibling leakage: `AverageLatency`, `MinLatency`, `MaxLatency`, and `99thPercentileLatency`.

Feature families include main-run counters, extend-phase counters, direct `.dbstats`, value-size tails, vacuum duration, p95 autoregressive terms, and selected lags. Feature count after mutual-information filtering: `92`.

## Walk-Forward Metrics, Initial Train 1-25

| model | n_predicted_epochs | mae_us | rmse_us | r2 | late_mae_us_epoch_80_100 | epoch97_pred_us | epoch97_abs_error_us |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `wide_ridge` | 75 | 79.700 | 143.600 | 0.907 | 206.900 | 2267.900 | 713.100 |

## Walk-Forward Metrics, Initial Train 1-70

| model | n_predicted_epochs | mae_us | rmse_us | r2 | late_mae_us_epoch_80_100 | epoch97_pred_us | epoch97_abs_error_us |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `wide_ridge` | 30 | 155.700 | 220.300 | 0.796 | 206.900 | 2267.900 | 713.100 |

## Top Mutual-Information Features

| feature | mutual_info |
| --- | --- |
| `main_Runtime(ms)` | 2.114 |
| `p95_roll10_mean_us` | 2.012 |
| `p95_roll5_mean_us` | 1.990 |
| `db_autovacuum_count` | 1.957 |
| `p95_lag1_us` | 1.937 |
| `p95_roll8_mean_us` | 1.918 |
| `main_checkpoint_write_time` | 1.913 |
| `delta_extend_checkpoints_req` | 1.905 |
| `delta_main_checkpoints_req` | 1.903 |
| `pct_gt_128k_lag1` | 1.901 |
| `extend_checkpoint_write_time` | 1.899 |
| `pct_gt_128k` | 1.899 |
| `p95_roll10_max_us` | 1.893 |
| `db_blks_hit` | 1.892 |
| `main_blks_hit` | 1.891 |

## Top Ridge Coefficients

| feature | standardized_coefficient_us | abs_coefficient |
| --- | --- | --- |
| `delta_main_tup_fetched` | -1977.100 | 1977.100 |
| `delta_main_tup_returned` | -1871.300 | 1871.300 |
| `delta_extend_wal_bytes` | -1229.200 | 1229.200 |
| `db_n_tup_hot_upd` | 1125.100 | 1125.100 |
| `main_Runtime(ms)` | 1021.700 | 1021.700 |
| `p95_roll8_mean_us` | 958.900 | 958.900 |
| `delta_main_checkpoints_req` | 908.500 | 908.500 |
| `delta_db_wal_bytes_gib_lag3` | -890.500 | 890.500 |
| `delta_db_wal_bytes_lag3` | -890.500 | 890.500 |
| `main_wal_buffers_full` | -887.900 | 887.900 |
| `db_toast_heap_bytes_gib` | 800.200 | 800.200 |
| `db_toast_heap_bytes` | 800.200 | 800.200 |
| `pct_gt_128k_lag2` | 787.200 | 787.200 |
| `p95_roll3_mean_us` | 771.000 | 771.000 |
| `delta_extend_tup_returned` | 705.800 | 705.800 |
