# Main-Run p95 Regression Model, Train 1-70

This rerun uses the same features as `model_main_run_p95_latency.py`, but holds epochs `71-100` out for prediction. The model is still walk-forward after epoch 70: each predicted epoch is trained on all prior epochs.

| model | predicted epochs | MAE us | RMSE us | R2 | epoch 97 abs error us |
| --- | --- | ---: | ---: | ---: | ---: |
| `gradient_boosting_arx` | `71-100` | 331.7 | 468.9 | 0.076 | 1304.7 |
| `ridge_arx` | `71-100` | 343.4 | 506.4 | -0.078 | 1341.0 |

Best by MAE: `gradient_boosting_arx`.

Outputs:

- `main_run_p95_latency_regression_predicted_vs_true_train70.png`
- `main_run_p95_latency_regression_predictions_train70.csv`
- `main_run_p95_latency_regression_metrics_train70.csv`
