from pathlib import Path
import csv
import re

import matplotlib.pyplot as plt
import pandas as pd


DATA_DIR = Path("DATA")
RESULTS_DIR = Path("results")

OPERATIONS = ["READ", "INSERT", "UPDATE", "EXTEND"]
METRICS = [
    ("AverageLatency(us)", "avg_latency_us", "Average Latency (us)"),
    ("MinLatency(us)", "min_latency_us", "Min Latency (us)"),
    ("MaxLatency(us)", "max_latency_us", "Max Latency (us)"),
    ("95thPercentileLatency(us)", "p95_latency_us", "P95 Latency (us)"),
    ("99thPercentileLatency(us)", "p99_latency_us", "P99 Latency (us)"),
    ("Throughput(ops/sec)", "throughput_ops_sec", "Throughput (ops/sec)"),
]


def parse_rows(csv_path: Path, metric_col_name: str) -> pd.DataFrame:
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return pd.DataFrame(columns=["Epoch", "Operation", "metric"])

        if metric_col_name not in header:
            raise ValueError(f"{metric_col_name} missing in {csv_path.name}")

        metric_idx = header.index(metric_col_name)

        for row in reader:
            if len(row) <= max(5, metric_idx):
                continue
            rows.append(
                {
                    "Epoch": row[0],
                    "Operation": row[5],
                    "metric": row[metric_idx],
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["Operation"] = df["Operation"].astype(str).str.upper()
    df["Epoch"] = pd.to_numeric(df["Epoch"], errors="coerce")
    df["metric"] = pd.to_numeric(df["metric"], errors="coerce")
    df = df.dropna(subset=["Epoch", "Operation", "metric"])
    return df


def make_plot(csv_path: Path, metric_col_name: str, metric_ylabel: str, output_dir: Path) -> Path:
    df = parse_rows(csv_path, metric_col_name)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=False, sharey=False)
    axes = axes.flatten()

    for ax, operation in zip(axes, OPERATIONS):
        op_df = df[df["Operation"] == operation]
        if op_df.empty:
            ax.set_title(operation)
            ax.set_xlabel("Epoch")
            ax.set_ylabel(metric_ylabel)
            ax.grid(False)
            continue

        by_epoch = op_df.groupby("Epoch", as_index=False)["metric"].mean().sort_values("Epoch")
        ax.plot(by_epoch["Epoch"], by_epoch["metric"], marker="o")
        ax.set_title(operation)
        ax.set_xlabel("Epoch")
        ax.set_ylabel(metric_ylabel)
        ax.grid(True, alpha=0.3)

    fig.suptitle(f"{csv_path.stem}: Epoch vs {metric_ylabel} by Operation", y=1.02)
    fig.tight_layout()

    metric_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", metric_col_name).strip("_")
    out_path = output_dir / f"{csv_path.stem}_epoch_vs_{metric_slug}.png"
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main() -> None:
    files = sorted(DATA_DIR.glob("postgresql_*.csv"))
    if not files:
        raise RuntimeError("No PostgreSQL files found in DATA/")

    total = 0
    for metric_col, folder_name, metric_label in METRICS:
        out_dir = RESULTS_DIR / f"postgresql_epoch_{folder_name}"
        out_dir.mkdir(parents=True, exist_ok=True)

        generated = []
        for csv_path in files:
            generated.append(make_plot(csv_path, metric_col, metric_label, out_dir))
            total += 1

        print(f"[{metric_col}] Generated {len(generated)} plot(s) in {out_dir}")

    print(f"Total generated plots: {total}")


if __name__ == "__main__":
    main()
