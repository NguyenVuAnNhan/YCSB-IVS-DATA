#!/usr/bin/env python3
"""Plot FULL_VIEW YCSB P95 latency against epoch."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BASE_DIR / "analysis"

RUNS = [
    ("full_view_run1", BASE_DIR / "full_view_run1" / "ycsb" / "full_view_run1_zipfian_heavy_pure.csv"),
    (
        "full_view_run2",
        BASE_DIR
        / "full_view_run2_3_106_232_96"
        / "ycsb"
        / "full_view_run2_zipfian_heavy_pure.csv",
    ),
]

PHASES = ["extend", "run", "reference"]
PHASE_TITLES = {
    "extend": "Extend phase",
    "run": "Measured read phase",
    "reference": "Reference read phase",
}


def load_p95() -> pd.DataFrame:
    frames = []
    for run_label, csv_path in RUNS:
        df = pd.read_csv(csv_path)
        needed = {"Epoch", "Phase", "95thPercentileLatency(us)"}
        missing = needed - set(df.columns)
        if missing:
            raise ValueError(f"{csv_path} is missing columns: {sorted(missing)}")

        df = df.loc[df["Phase"].isin(PHASES), ["Epoch", "Phase", "95thPercentileLatency(us)"]].copy()
        df["run"] = run_label
        df["epoch"] = pd.to_numeric(df["Epoch"], errors="coerce").astype("Int64")
        df["p95_latency_ms"] = pd.to_numeric(df["95thPercentileLatency(us)"], errors="coerce") / 1000.0
        df = df.dropna(subset=["epoch", "p95_latency_ms"])
        frames.append(df[["run", "epoch", "Phase", "p95_latency_ms"]].rename(columns={"Phase": "phase"}))

    out = pd.concat(frames, ignore_index=True)
    out["phase"] = pd.Categorical(out["phase"], categories=PHASES, ordered=True)
    out = out.sort_values(["run", "phase", "epoch"]).reset_index(drop=True)
    return out


def add_epoch_group_lines(ax: plt.Axes) -> None:
    for epoch in range(10, 100, 10):
        ax.axvline(epoch, color="#d8d8d8", linewidth=0.7, zorder=0)


def plot_all_phases(df: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(len(PHASES), 1, figsize=(11, 8.4), sharex=True, constrained_layout=True)
    colors = {"full_view_run1": "#1f77b4", "full_view_run2": "#d95f02"}

    for ax, phase in zip(axes, PHASES):
        phase_df = df[df["phase"] == phase]
        for run_label, run_df in phase_df.groupby("run", observed=True):
            ax.plot(
                run_df["epoch"],
                run_df["p95_latency_ms"],
                label=run_label,
                color=colors.get(run_label),
                linewidth=1.8,
            )
        add_epoch_group_lines(ax)
        ax.set_title(PHASE_TITLES[phase], loc="left", fontsize=11)
        ax.set_ylabel("P95 latency (ms)")
        ax.grid(axis="y", color="#e8e8e8", linewidth=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    axes[0].legend(loc="upper left", frameon=False, ncols=2)
    axes[-1].set_xlabel("Epoch")
    axes[-1].set_xlim(1, 100)
    fig.suptitle("FULL_VIEW P95 Latency by Epoch", fontsize=14, fontweight="bold")

    out_path = OUT_DIR / "full_view_p95_latency_by_epoch.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def plot_run_phase(df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.8), constrained_layout=True)
    colors = {"full_view_run1": "#1f77b4", "full_view_run2": "#d95f02"}
    run_df = df[df["phase"] == "run"]

    for run_label, group in run_df.groupby("run", observed=True):
        ax.plot(
            group["epoch"],
            group["p95_latency_ms"],
            label=run_label,
            color=colors.get(run_label),
            linewidth=2.0,
        )

    add_epoch_group_lines(ax)
    ax.set_title("FULL_VIEW Measured Read Phase: P95 Latency by Epoch", fontsize=13, fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("P95 latency (ms)")
    ax.set_xlim(1, 100)
    ax.grid(axis="y", color="#e8e8e8", linewidth=0.8)
    ax.legend(loc="upper left", frameon=False, ncols=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    out_path = OUT_DIR / "full_view_run_phase_p95_latency_by_epoch.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def main() -> None:
    df = load_p95()
    tidy_path = OUT_DIR / "full_view_p95_latency_by_epoch.csv"
    df.to_csv(tidy_path, index=False)
    all_phase_plot = plot_all_phases(df)
    run_phase_plot = plot_run_phase(df)
    print(tidy_path)
    print(all_phase_plot)
    print(run_phase_plot)


if __name__ == "__main__":
    main()
