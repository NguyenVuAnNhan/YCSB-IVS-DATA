# Main-Run p95 Grouped Regression Split

Split design: five 20-epoch groups. In each group, train on the first 10 epochs, test on the next 5, validate on the last 5.

Grey bands in the plot are each group's 10-epoch training windows. Prediction markers are out-of-sample points from that group's trained model.

## Overall Metrics

| model | phase | n | MAE us | RMSE us | R2 |
| --- | --- | ---: | ---: | ---: | ---: |
| `gradient_boosting` | `test` | 25 | 94.1 | 160.4 | 0.825 |
| `ridge` | `test` | 25 | 253.8 | 505.3 | -0.742 |
| `gradient_boosting` | `test+validate` | 50 | 136.8 | 289.5 | 0.655 |
| `ridge` | `test+validate` | 50 | 440.5 | 902.4 | -2.35 |
| `gradient_boosting` | `validate` | 25 | 179.5 | 376.8 | 0.572 |
| `ridge` | `validate` | 25 | 627.1 | 1171.9 | -3.139 |

## Per-Group Metrics

| model | group | phase | epochs | MAE us | RMSE us |
| --- | ---: | --- | --- | ---: | ---: |
| `gradient_boosting` | 1 | `test` | `11-15` | 31.9 | 34.2 |
| `gradient_boosting` | 1 | `validate` | `16-20` | 70.1 | 71.1 |
| `gradient_boosting` | 2 | `test` | `31-35` | 26.5 | 27.3 |
| `gradient_boosting` | 2 | `validate` | `36-40` | 55.8 | 56.3 |
| `gradient_boosting` | 3 | `test` | `51-55` | 52.3 | 62.9 |
| `gradient_boosting` | 3 | `validate` | `56-60` | 191.1 | 218.4 |
| `gradient_boosting` | 4 | `test` | `71-75` | 176.6 | 184.7 |
| `gradient_boosting` | 4 | `validate` | `76-80` | 69.9 | 116.7 |
| `gradient_boosting` | 5 | `test` | `91-95` | 183.0 | 297.7 |
| `gradient_boosting` | 5 | `validate` | `96-100` | 510.6 | 800.1 |
| `ridge` | 1 | `test` | `11-15` | 37.6 | 41.6 |
| `ridge` | 1 | `validate` | `16-20` | 46.1 | 49.8 |
| `ridge` | 2 | `test` | `31-35` | 5.1 | 5.3 |
| `ridge` | 2 | `validate` | `36-40` | 8.6 | 9.3 |
| `ridge` | 3 | `test` | `51-55` | 72.5 | 88.6 |
| `ridge` | 3 | `validate` | `56-60` | 121.8 | 123.1 |
| `ridge` | 4 | `test` | `71-75` | 293.6 | 400.0 |
| `ridge` | 4 | `validate` | `76-80` | 704.5 | 705.1 |
| `ridge` | 5 | `test` | `91-95` | 860.6 | 1052.2 |
| `ridge` | 5 | `validate` | `96-100` | 2254.4 | 2520.4 |

## Outputs

- `main_run_p95_latency_grouped_10train_5test_5validate.png`
- `main_run_p95_latency_grouped_10train_5test_5validate_predictions.csv`
- `main_run_p95_latency_grouped_10train_5test_5validate_metrics.csv`
- `main_run_p95_latency_grouped_10train_5test_5validate_group_metrics.csv`
- `main_run_p95_latency_grouped_10train_5test_5validate_splits.csv`
