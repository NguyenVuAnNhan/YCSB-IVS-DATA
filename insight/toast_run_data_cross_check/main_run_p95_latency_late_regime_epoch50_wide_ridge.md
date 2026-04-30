# Late-Regime Wide Ridge Model, Epoch 50+

This rerun trains/tests only on the apparent late regime beginning at epoch 50. It reuses the wide CSV/dbstats feature set while excluding latency-sibling leakage.

Two walk-forward cuts are shown:

- train epochs `50-69`, predict `70-100`
- train epochs `50-79`, predict `80-100`

## Metrics

| initial_train_epochs | predicted_epoch_range | n_predicted_epochs | mae_us | rmse_us | r2 | late_mae_us_epoch_80_100 | epoch97_pred_us | epoch97_abs_error_us |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | `70-100` | 31 | 154.800 | 241.700 | 0.747 | 209.500 | 2120.800 | 860.200 |
| 30 | `80-100` | 21 | 209.500 | 291.700 | 0.711 | 209.500 | 2120.800 | 860.200 |

## Top Late-Regime Ridge Coefficients

| feature | standardized_coefficient_us | abs_coefficient |
| --- | --- | --- |
| `delta_extend_wal_bytes` | -1546.400 | 1546.400 |
| `delta_main_tup_returned` | -1468.100 | 1468.100 |
| `delta_main_tup_fetched` | -1432.000 | 1432.000 |
| `db_n_tup_hot_upd` | 952.300 | 952.300 |
| `main_Runtime(ms)` | 844.500 | 844.500 |
| `pct_gt_128k_lag2` | 777.500 | 777.500 |
| `p95_roll8_mean_us` | 696.600 | 696.600 |
| `delta_main_tup_inserted` | 659.200 | 659.200 |
| `delta_extend_tup_inserted` | 659.000 | 659.000 |
| `delta_main_tup_deleted` | 650.200 | 650.200 |
| `delta_extend_tup_deleted` | 650.000 | 650.000 |
| `delta_db_wal_bytes_gib_lag3` | -641.800 | 641.800 |
| `delta_db_wal_bytes_lag3` | -641.800 | 641.800 |
| `delta_main_checkpoints_req` | 588.300 | 588.300 |
| `extend_wal_buffers_full` | -542.300 | 542.300 |
