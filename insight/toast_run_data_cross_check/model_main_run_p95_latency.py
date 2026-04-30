#!/usr/bin/env python3
"""Model main-run p95 latency against TOAST/storage features.

This produces expanding-window, out-of-sample predictions. For epoch N, the
model trains only on epochs before N, then predicts epoch N using current
storage/value-size measurements and prior latency lags.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


BASE = Path(__file__).resolve().parents[2]
TOAST_DATA = BASE / "TOAST_RUN_DATA"
OUTDIR = Path(__file__).resolve().parent

COMBINED_CSV = TOAST_DATA / "postgresql_arrayjson_TOAST_run1_zipfian_heavy_pure.csv"
RUN_DBSTATS = TOAST_DATA / "ycsb_postgresql_arrayjson_TOAST_zipfian_heavy_pure_run1_run.dbstats"
VALUE_SIZES = TOAST_DATA / "value_sizes_postgresql_arrayjson_TOAST_run1_zipfian_heavy_after_pure.csv"
RESULTS_LOG = TOAST_DATA / "ycsb_postgresql_arrayjson_TOAST_zipfian_heavy_pure_run1_results.log"

PREDICTIONS_CSV = OUTDIR / "main_run_p95_latency_regression_predictions.csv"
METRICS_CSV = OUTDIR / "main_run_p95_latency_regression_metrics.csv"
COEFFICIENTS_CSV = OUTDIR / "main_run_p95_latency_ridge_coefficients.csv"
PLOT_PNG = OUTDIR / "main_run_p95_latency_regression_predicted_vs_true.png"
SUMMARY_MD = OUTDIR / "main_run_p95_latency_regression_model.md"


def parse_vacuum_seconds() -> pd.DataFrame:
    text = RESULTS_LOG.read_text()
    starts = [int(x) for x in re.findall(r"VACUUM start: (\\d+)", text)]
    ends = [int(x) for x in re.findall(r"VACUUM end: (\\d+)", text)]
    n = min(len(starts), len(ends))
    return pd.DataFrame(
        {
            "Epoch": np.arange(1, n + 1),
            "vacuum_seconds": [ends[i] - starts[i] for i in range(n)],
        }
    )


def load_model_frame() -> pd.DataFrame:
    combined = pd.read_csv(COMBINED_CSV)
    latency = (
        combined[combined["Phase"] == "run"][
            [
                "Epoch",
                "95thPercentileLatency(us)",
                "AverageLatency(us)",
                "99thPercentileLatency(us)",
                "Throughput(ops/sec)",
            ]
        ]
        .sort_values("Epoch")
        .copy()
    )
    latency = latency.rename(columns={"95thPercentileLatency(us)": "p95_us"})

    db = pd.read_csv(RUN_DBSTATS)
    db = db[db["numbackends"] == 0].sort_values("Epoch").copy()
    db["toast_total_gib"] = db["toast_total_bytes"] / 1024**3
    db["toast_heap_gib"] = db["toast_heap_bytes"] / 1024**3
    db["toast_index_gib"] = db["toast_index_bytes"] / 1024**3
    for col in [
        "toast_total_bytes",
        "blks_read",
        "blks_hit",
        "buffers_alloc",
        "wal_bytes",
        "wal_records",
        "temp_bytes",
    ]:
        db[f"delta_{col}"] = db[col].diff()
    first = db.index[0]
    db.loc[first, "delta_toast_total_bytes"] = db.loc[first, "toast_total_bytes"]
    for col in [
        "delta_blks_read",
        "delta_blks_hit",
        "delta_buffers_alloc",
        "delta_wal_bytes",
        "delta_wal_records",
        "delta_temp_bytes",
    ]:
        db.loc[first, col] = 0

    db["delta_toast_total_gib"] = db["delta_toast_total_bytes"] / 1024**3
    db["delta_blks_read_m"] = db["delta_blks_read"] / 1_000_000
    db["delta_blks_hit_m"] = db["delta_blks_hit"] / 1_000_000
    db["delta_buffers_alloc_m"] = db["delta_buffers_alloc"] / 1_000_000
    db["delta_wal_gib"] = db["delta_wal_bytes"] / 1024**3
    db["delta_temp_mib"] = db["delta_temp_bytes"] / 1024**2

    values = pd.read_csv(VALUE_SIZES)
    value_rows = []
    for epoch in range(1, 101):
        s = values[f"Run{epoch}"]
        value_rows.append(
            {
                "Epoch": epoch,
                "value_mean_kib": s.mean() / 1024,
                "value_p95_kib": s.quantile(0.95) / 1024,
                "value_p99_kib": s.quantile(0.99) / 1024,
                "value_max_mib": s.max() / 1024**2,
                "pct_rows_gt_128k": (s > 128 * 1024).mean(),
            }
        )
    value_df = pd.DataFrame(value_rows)

    frame = (
        latency.merge(
            db[
                [
                    "Epoch",
                    "toast_total_gib",
                    "toast_heap_gib",
                    "toast_index_gib",
                    "delta_toast_total_gib",
                    "delta_blks_read_m",
                    "delta_blks_hit_m",
                    "delta_buffers_alloc_m",
                    "delta_wal_gib",
                    "delta_temp_mib",
                ]
            ],
            on="Epoch",
        )
        .merge(value_df, on="Epoch")
        .merge(parse_vacuum_seconds(), on="Epoch", how="left")
        .sort_values("Epoch")
    )

    frame["p95_lag1_us"] = frame["p95_us"].shift(1)
    frame["p95_lag2_us"] = frame["p95_us"].shift(2)
    frame["p95_roll3_us"] = frame["p95_us"].shift(1).rolling(3, min_periods=1).mean()
    frame["delta_toast_lag1_gib"] = frame["delta_toast_total_gib"].shift(1)
    frame["vacuum_lag1_seconds"] = frame["vacuum_seconds"].shift(1)
    frame = frame.fillna(0)
    return frame


FEATURES = [
    "Epoch",
    "toast_total_gib",
    "delta_toast_total_gib",
    "delta_toast_lag1_gib",
    "value_p95_kib",
    "value_p99_kib",
    "value_max_mib",
    "pct_rows_gt_128k",
    "vacuum_seconds",
    "vacuum_lag1_seconds",
    "delta_blks_read_m",
    "delta_blks_hit_m",
    "delta_buffers_alloc_m",
    "delta_wal_gib",
    "delta_temp_mib",
    "p95_lag1_us",
    "p95_lag2_us",
    "p95_roll3_us",
]


def make_models() -> dict[str, object]:
    ridge = make_pipeline(
        StandardScaler(),
        RidgeCV(alphas=np.logspace(-3, 4, 80)),
    )
    gbr = GradientBoostingRegressor(
        random_state=7,
        n_estimators=350,
        learning_rate=0.025,
        max_depth=2,
        min_samples_leaf=4,
        subsample=0.85,
    )
    return {
        "ridge_arx": ridge,
        "gradient_boosting_arx": gbr,
    }


def expanding_window_predictions(frame: pd.DataFrame, min_train: int = 25) -> pd.DataFrame:
    rows = []
    models = make_models()
    for i in range(min_train, len(frame)):
        train = frame.iloc[:i]
        test = frame.iloc[[i]]
        result = {
            "Epoch": int(test["Epoch"].iloc[0]),
            "true_p95_us": float(test["p95_us"].iloc[0]),
        }
        for name, model in models.items():
            fitted = model.fit(train[FEATURES], train["p95_us"])
            result[f"pred_{name}_us"] = float(fitted.predict(test[FEATURES])[0])
        rows.append(result)
    return pd.DataFrame(rows)


def score_predictions(pred: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in [c for c in pred.columns if c.startswith("pred_")]:
        y = pred["true_p95_us"]
        yhat = pred[col]
        rows.append(
            {
                "model": col.removeprefix("pred_").removesuffix("_us"),
                "n_predicted_epochs": len(pred),
                "mae_us": mean_absolute_error(y, yhat),
                "rmse_us": math.sqrt(mean_squared_error(y, yhat)),
                "r2": r2_score(y, yhat),
                "late_mae_us_epoch_80_100": mean_absolute_error(
                    pred[pred["Epoch"] >= 80]["true_p95_us"],
                    pred[pred["Epoch"] >= 80][col],
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("mae_us")


def write_ridge_coefficients(frame: pd.DataFrame) -> None:
    model = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-3, 4, 80)))
    model.fit(frame[FEATURES], frame["p95_us"])
    ridge = model.named_steps["ridgecv"]
    coefs = pd.DataFrame(
        {
            "feature": FEATURES,
            "standardized_coefficient_us": ridge.coef_,
            "abs_coefficient": np.abs(ridge.coef_),
        }
    ).sort_values("abs_coefficient", ascending=False)
    coefs.to_csv(COEFFICIENTS_CSV, index=False)


def plot_predictions(frame: pd.DataFrame, pred: pd.DataFrame, best_col: str) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=160)

    ax.plot(frame["Epoch"], frame["p95_us"], color="#222222", linewidth=2.4, label="true p95")
    ax.plot(
        pred["Epoch"],
        pred[best_col],
        color="#d62728",
        linewidth=2.3,
        label=best_col.removeprefix("pred_").removesuffix("_us").replace("_", " "),
    )
    other_cols = [c for c in pred.columns if c.startswith("pred_") and c != best_col]
    for col in other_cols:
        ax.plot(
            pred["Epoch"],
            pred[col],
            color="#4c78a8",
            linewidth=1.7,
            alpha=0.75,
            linestyle="--",
            label=col.removeprefix("pred_").removesuffix("_us").replace("_", " "),
        )

    ax.axvspan(1, 25, color="#eeeeee", alpha=0.8, label="initial training window")
    ax.axhline(1000, color="#777777", linewidth=1, linestyle=":", label="1000 us threshold")
    ax.set_title("Main Run p95 Latency: True vs Walk-Forward Regression Prediction", fontsize=15, pad=12)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("p95 latency (us)")
    ax.set_xlim(1, 100)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:,.0f}"))
    ax.legend(frameon=True, loc="upper left", ncol=2)
    ax.grid(True, axis="y", color="#d9d9d9", linewidth=0.8)
    ax.grid(False, axis="x")
    ax.spines[["top", "right"]].set_visible(False)

    peak = frame.loc[frame["p95_us"].idxmax()]
    ax.annotate(
        f"true peak {peak['p95_us']:.0f} us",
        xy=(peak["Epoch"], peak["p95_us"]),
        xytext=(-72, -38),
        textcoords="offset points",
        fontsize=8,
        arrowprops=dict(arrowstyle="->", color="#555555", lw=0.9),
    )

    fig.tight_layout()
    fig.savefig(PLOT_PNG, bbox_inches="tight")


def write_summary(metrics: pd.DataFrame, best_model: str) -> None:
    best = metrics.iloc[0]
    coefs = pd.read_csv(COEFFICIENTS_CSV).head(8)
    coef_lines = "\n".join(
        f"- `{row.feature}`: `{row.standardized_coefficient_us:.1f}`"
        for row in coefs.itertuples(index=False)
    )
    rounded_metrics = metrics.round(
        {"mae_us": 1, "rmse_us": 1, "r2": 3, "late_mae_us_epoch_80_100": 1}
    )
    metric_header = "| model | n_predicted_epochs | mae_us | rmse_us | r2 | late_mae_us_epoch_80_100 |"
    metric_sep = "| --- | ---: | ---: | ---: | ---: | ---: |"
    metric_rows = []
    for row in rounded_metrics.itertuples(index=False):
        metric_rows.append(
            f"| `{row.model}` | {row.n_predicted_epochs} | {row.mae_us} | "
            f"{row.rmse_us} | {row.r2} | {row.late_mae_us_epoch_80_100} |"
        )
    metric_table = "\n".join([metric_header, metric_sep, *metric_rows])
    SUMMARY_MD.write_text(
        f"""# Main-Run p95 Regression Model

This model predicts main-run p95 latency using an expanding-window time-series setup. Epochs 1-25 are the initial training window; each later epoch is predicted by training on all earlier epochs only.

## Inputs

- TOAST total size and epoch-to-epoch TOAST growth
- value-size tail statistics: p95, p99, max, and fraction above 128 KiB
- vacuum duration and lagged vacuum duration
- storage counter deltas: block reads/hits, buffer allocations, WAL bytes, temp bytes
- autoregressive p95 terms: lag-1, lag-2, and prior 3-epoch rolling mean

## Metrics

{metric_table}

Best walk-forward model by MAE: `{best_model}` with MAE `{best.mae_us:.1f} us` and late-epoch MAE `{best.late_mae_us_epoch_80_100:.1f} us`.

## Ridge Coefficients

Top standardized ridge coefficients from the full fitted model:

{coef_lines}

## Outputs

- `main_run_p95_latency_regression_predicted_vs_true.png`
- `main_run_p95_latency_regression_predictions.csv`
- `main_run_p95_latency_regression_metrics.csv`
- `main_run_p95_latency_ridge_coefficients.csv`
"""
    )

def main() -> None:
    OUTDIR.mkdir(exist_ok=True)
    frame = load_model_frame()
    pred = expanding_window_predictions(frame)
    metrics = score_predictions(pred)
    best_model = metrics.iloc[0]["model"]
    best_col = f"pred_{best_model}_us"
    write_ridge_coefficients(frame)
    pred.to_csv(PREDICTIONS_CSV, index=False)
    metrics.to_csv(METRICS_CSV, index=False)
    plot_predictions(frame, pred, best_col)
    write_summary(metrics, best_model)

    print(PLOT_PNG)
    print(PREDICTIONS_CSV)
    print(METRICS_CSV)
    print(COEFFICIENTS_CSV)
    print(SUMMARY_MD)
    print(metrics.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
