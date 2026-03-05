from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import re

import matplotlib.pyplot as plt
import pandas as pd


DATA_DIR = Path("DATA")
RESULTS_DIR = Path("results")
OPERATIONS = ["READ", "INSERT", "UPDATE", "EXTEND"]

METRICS = [
    ("avg_latency_us", "AverageLatency(us)"),
    ("min_latency_us", "MinLatency(us)"),
    ("max_latency_us", "MaxLatency(us)"),
    ("p95", "95thPercentileLatency(us)"),
    ("p95_latency_us", "95thPercentileLatency(us)"),
    ("p99_latency_us", "99thPercentileLatency(us)"),
    ("throughput_ops_sec", "Throughput(ops/sec)"),
]


@dataclass
class Dataset:
    run: int
    scenario_raw: str
    scenario_base: str
    csv_path: Path
    assigned_run: int = -1


def discover_datasets(db: str) -> list[Dataset]:
    files = sorted(DATA_DIR.glob(f"{db}_run*_*.csv"))
    datasets: list[Dataset] = []
    pat = re.compile(rf"^{re.escape(db)}_run(\d+)_(.+)\.csv$")

    for f in files:
        m = pat.match(f.name)
        if not m:
            continue
        run = int(m.group(1))
        scenario_raw = m.group(2)
        scenario_base = scenario_raw[:-4] if scenario_raw.endswith("_dup") else scenario_raw
        datasets.append(
            Dataset(run=run, scenario_raw=scenario_raw, scenario_base=scenario_base, csv_path=f)
        )
    return datasets


def assign_runs(datasets: list[Dataset]) -> None:
    by_scenario: dict[str, list[Dataset]] = {}
    for d in datasets:
        by_scenario.setdefault(d.scenario_base, []).append(d)

    for scenario, items in by_scenario.items():
        regular = sorted([x for x in items if not x.scenario_raw.endswith("_dup")], key=lambda x: x.run)
        dup = sorted([x for x in items if x.scenario_raw.endswith("_dup")], key=lambda x: x.run)

        max_regular = max([x.run for x in regular], default=0)
        for r in regular:
            r.assigned_run = r.run

        next_run = max_regular + 1
        for d in dup:
            d.assigned_run = next_run
            next_run += 1


def parse_metric_rows(csv_path: Path, metric_col: str, run_id: int) -> pd.DataFrame:
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header or metric_col not in header:
            return pd.DataFrame(columns=["run", "Epoch", "Operation", "value"])
        idx = header.index(metric_col)

        for row in reader:
            if len(row) <= max(5, idx):
                continue
            rows.append({"run": run_id, "Epoch": row[0], "Operation": row[5], "value": row[idx]})

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Epoch"] = pd.to_numeric(df["Epoch"], errors="coerce")
    df["Operation"] = df["Operation"].astype(str).str.upper()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["Epoch", "Operation", "value"])


def plot_run(df: pd.DataFrame, out_path: Path, title: str, ylabel: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=False, sharey=False)
    axes = axes.flatten()

    for ax, op in zip(axes, OPERATIONS):
        op_df = df[df["Operation"] == op]
        ax.set_title(op)
        ax.set_xlabel("Epoch")
        ax.set_ylabel(ylabel)
        if op_df.empty:
            ax.grid(False)
            continue
        by_epoch = op_df.groupby("Epoch", as_index=False)["value"].mean().sort_values("Epoch")
        ax.plot(by_epoch["Epoch"], by_epoch["value"], marker="o")
        ax.grid(True, alpha=0.3)

    fig.suptitle(title, y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def summarize_runs(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=["Operation", "Epoch", "mean", "sd"])

    all_df = pd.concat(frames, ignore_index=True)
    per_run = (
        all_df.groupby(["run", "Operation", "Epoch"], as_index=False)["value"]
        .mean()
        .sort_values(["run", "Operation", "Epoch"])
    )
    summary = (
        per_run.groupby(["Operation", "Epoch"])["value"]
        .agg(["mean", lambda s: s.std(ddof=1)])
        .reset_index()
        .sort_values(["Operation", "Epoch"])
    )
    lambda_col = [c for c in summary.columns if c not in ("Operation", "Epoch", "mean")]
    if lambda_col:
        summary = summary.rename(columns={lambda_col[0]: "sd"})
    else:
        summary["sd"] = 0.0
    summary["sd"] = summary["sd"].fillna(0.0)
    return summary


def plot_summary(summary: pd.DataFrame, out_path: Path, title: str, ylabel: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=False, sharey=False)
    axes = axes.flatten()

    for ax, op in zip(axes, OPERATIONS):
        op_df = summary[summary["Operation"] == op]
        ax.set_title(op)
        ax.set_xlabel("Epoch")
        ax.set_ylabel(ylabel)
        if op_df.empty:
            ax.grid(False)
            continue

        x = op_df["Epoch"]
        mean = op_df["mean"]
        band = 2.0 * op_df["sd"]
        ax.plot(x, mean, marker="o", label="mean")
        ax.fill_between(x, mean - band, mean + band, alpha=0.2, label="mean ± 2*sd")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=8)

    fig.suptitle(title, y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def generate_for_db(db: str) -> None:
    datasets = discover_datasets(db)
    if not datasets:
        raise RuntimeError(f"No datasets found for db={db}")
    assign_runs(datasets)

    by_scenario: dict[str, list[Dataset]] = {}
    for d in datasets:
        by_scenario.setdefault(d.scenario_base, []).append(d)
    for v in by_scenario.values():
        v.sort(key=lambda x: x.assigned_run)

    db_root = RESULTS_DIR / db
    db_root.mkdir(parents=True, exist_ok=True)

    for metric_slug, metric_col in METRICS:
        metric_root = db_root / f"{db}_epoch_{metric_slug}"
        metric_root.mkdir(parents=True, exist_ok=True)

        for scenario, scenario_items in sorted(by_scenario.items()):
            scenario_dir = metric_root / scenario
            raw_dir = scenario_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)

            run_frames = []
            for item in scenario_items:
                df = parse_metric_rows(item.csv_path, metric_col, item.assigned_run)
                run_frames.append(df)
                run_out = raw_dir / f"{db}_run{item.assigned_run}_{scenario}_epoch_vs_{metric_slug}.png"
                plot_run(
                    df=df,
                    out_path=run_out,
                    title=f"{db} run{item.assigned_run} {scenario}: {metric_col}",
                    ylabel=metric_col,
                )

            summary = summarize_runs(run_frames)
            summary_out = scenario_dir / "summary_mean_plusminus_2sd.png"
            plot_summary(
                summary=summary,
                out_path=summary_out,
                title=f"{db}/{metric_slug}/{scenario}: mean ± 2*sd",
                ylabel=metric_col,
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", choices=["postgresql", "neo4j"], required=True)
    args = parser.parse_args()
    generate_for_db(args.db)
    print(f"Completed generation for {args.db}")


if __name__ == "__main__":
    main()
