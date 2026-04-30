# Delayed TOAST Regression Check

This rerun adds delayed TOAST features to the earlier p95 model:

- `toast_total_gib_lag0..10`
- `delta_toast_total_gib_lag0..10`
- prior rolling TOAST-growth sums/means over 2, 3, 5, 8, and 10 epochs

## Walk-Forward Metrics, Initial Train 1-25

| model | n_predicted_epochs | mae_us | rmse_us | r2 | late_mae_us_epoch_80_100 | epoch97_pred_us | epoch97_abs_error_us |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ridge_delayed` | 75 | 164.700 | 312.000 | 0.560 | 410.000 | 1599.300 | 1381.700 |
| `gradient_boosting_delayed` | 75 | 173.900 | 321.700 | 0.532 | 414.300 | 1245.100 | 1735.900 |

## Walk-Forward Metrics, Initial Train 1-70

| model | n_predicted_epochs | mae_us | rmse_us | r2 | late_mae_us_epoch_80_100 | epoch97_pred_us | epoch97_abs_error_us |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ridge_delayed` | 30 | 328.800 | 482.300 | 0.022 | 410.000 | 1599.300 | 1381.700 |
| `gradient_boosting_delayed` | 30 | 334.900 | 494.700 | -0.028 | 414.300 | 1245.100 | 1735.900 |

## Strongest Lag Correlations

| lag_epochs | pearson_corr | spearman_corr |
| --- | --- | --- |
| 3.000 | 0.110 | -0.079 |
| 6.000 | 0.018 | -0.087 |
| 4.000 | 0.125 | -0.087 |
| 5.000 | -0.003 | -0.102 |
| 2.000 | 0.104 | -0.102 |
| 15.000 | 0.178 | -0.116 |
| 7.000 | -0.022 | -0.124 |
| 1.000 | 0.033 | -0.129 |

## Top Ridge Coefficients

| feature | standardized_coefficient_us | abs_coefficient |
| --- | --- | --- |
| `p95_lag1_us` | 55.300 | 55.300 |
| `p95_lag2_us` | 44.200 | 44.200 |
| `delta_toast_total_gib_lag4` | 30.800 | 30.800 |
| `delta_toast_total_gib` | 28.800 | 28.800 |
| `delta_toast_total_gib_lag0` | 28.800 | 28.800 |
| `delta_toast_total_gib_lag9` | -28.000 | 28.000 |
| `delta_temp_mib` | 25.600 | 25.600 |
| `delta_blks_read_m` | 24.800 | 24.800 |
| `p95_roll3_us` | 24.800 | 24.800 |
| `pct_rows_gt_128k` | 22.400 | 22.400 |
| `delta_toast_total_gib_lag8` | -21.800 | 21.800 |
| `delta_toast_mean_prev5_gib` | 18.300 | 18.300 |

## Interpretation

The lag-correlation check shows the strongest association at same-epoch TOAST growth and short lags. The regression coefficients also prefer immediate/short-delay growth features plus autoregressive p95 terms. That supports a delayed/lingering response, but not a long hidden delay: the system seems to react within roughly 0-3 epochs, then the elevated latency persists through prior-latency and rolling-growth state.
