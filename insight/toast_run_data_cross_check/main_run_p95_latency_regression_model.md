# Main-Run p95 Regression Model

This model predicts main-run p95 latency using an expanding-window time-series setup. Epochs 1-25 are the initial training window; each later epoch is predicted by training on all earlier epochs only.

## Inputs

-   TOAST total size and epoch-to-epoch TOAST growth
-   value-size tail statistics: p95, p99, max, and fraction above 128 KiB
-   vacuum duration and lagged vacuum duration
-   storage counter deltas: block reads/hits, buffer allocations, WAL bytes, temp bytes
-   autoregressive p95 terms: lag-1, lag-2, and prior 3-epoch rolling mean

## Metrics

| model | n_predicted_epochs | mae_us | rmse_us | r2 | late_mae_us_epoch_80_100 |
|------------|-----------:|-----------:|-----------:|-----------:|-----------:|
| `ridge_arx` | 75 | 168.8 | 326.7 | 0.517 | 426.6 |
| `gradient_boosting_arx` | 75 | 169.5 | 305.0 | 0.579 | 404.7 |

Best walk-forward model by MAE: `ridge_arx` with MAE `168.8 us` and late-epoch MAE `426.6 us`.

## Ridge Coefficients

Top standardized ridge coefficients from the full fitted model:

-   `p95_lag1_us`: `70.0`
-   `p95_lag2_us`: `51.3`
-   `delta_toast_total_gib`: `39.9`
-   `delta_temp_mib`: `35.9`
-   `delta_blks_read_m`: `32.2`
-   `p95_roll3_us`: `30.8`
-   `pct_rows_gt_128k`: `29.5`
-   `toast_total_gib`: `21.3`

## Outputs

-   `main_run_p95_latency_regression_predicted_vs_true.png`
-   `main_run_p95_latency_regression_predictions.csv`
-   `main_run_p95_latency_regression_metrics.csv`
-   `main_run_p95_latency_ridge_coefficients.csv`