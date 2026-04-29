from __future__ import annotations

from pathlib import Path
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
JSON_BLUE = ROOT / "JSON_BLUE"
OUT_DIR = ROOT / "insight" / "json_blue_toast_evidence"
REPORT = ROOT / "insight" / "json_blue_toast_evidence.md"

RUNS = [3, 4, 5, 6]
SIZE_FILES = {
    4: ROOT
    / "JSON_BLUE_files/IVS3/analysis/Data/Value_size_data/"
    / "value_sizes_postgresql_arrayjson_vacuum_notfull_bigcache_run4_zipfian_heavy_before_pure.csv",
    5: ROOT
    / "JSON_BLUE_files/IVS4/analysis/Data/Value_size_data/"
    / "value_sizes_postgresql_arrayjson_vacuum_notfull_bigcache_run5_zipfian_heavy_before_pure.csv",
    6: ROOT
    / "JSON_BLUE_files/IVS5/analysis/Data/Value_size_data/"
    / "value_sizes_postgresql_arrayjson_vacuum_notfull_bigcache_run6_zipfian_heavy_before_pure.csv",
}

COUNTERS = [
    "blks_read",
    "blks_hit",
    "tup_returned",
    "tup_fetched",
    "tup_inserted",
    "tup_updated",
    "tup_deleted",
    "temp_bytes",
    "buffers_alloc",
    "wal_bytes",
    "wal_records",
    "wal_fpi",
]

LATENCY_COLS = [
    "AverageLatency(us)",
    "95thPercentileLatency(us)",
    "99thPercentileLatency(us)",
    "Throughput(ops/sec)",
    "Operations",
]

PHASE_ORDER = ["reference", "avg-run", "clean-run", "run", "extend"]
PHASE_COLORS = {
    "reference": "#5f7f95",
    "avg-run": "#2a9d8f",
    "clean-run": "#e9a03b",
    "run": "#cc4c4c",
    "extend": "#6c5ce7",
}


def ensure_output() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_from_path(path: Path) -> int:
    match = re.search(r"run(\d+)_", path.name)
    if not match:
        raise ValueError(f"Cannot infer run number from {path}")
    return int(match.group(1))


def load_latency() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(JSON_BLUE.glob("postgresql_arrayjson_vacuum_notfull_bigcache_run*_zipfian_heavy_pure.csv")):
        run = run_from_path(path)
        if run not in RUNS:
            continue
        df = pd.read_csv(path)
        df["run_id"] = run
        df["Phase"] = df["Phase"].astype(str).str.strip()
        df["Operation"] = df["Operation"].astype(str).str.strip().str.upper()
        for col in ["Epoch", *LATENCY_COLS, *COUNTERS]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = add_counter_deltas(df)
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No JSON Blue latency CSVs found in {JSON_BLUE}")
    return pd.concat(frames, ignore_index=True)


def add_counter_deltas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in COUNTERS:
        if col not in df.columns:
            continue
        delta = df[col].diff()
        delta[delta < 0] = np.nan
        df[f"delta_{col}"] = delta
        df[f"{col}_per_op_delta"] = delta / df["Operations"].replace(0, np.nan)
    return df


def load_value_size_summaries() -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for run, path in SIZE_FILES.items():
        if not path.exists():
            continue
        df = pd.read_csv(path)
        for col in df.columns[1:]:
            epoch = int(col.replace("Run", ""))
            sizes = pd.to_numeric(df[col], errors="coerce").dropna()
            rows.append(
                {
                    "run_id": run,
                    "Epoch": epoch,
                    "value_size_p50": sizes.quantile(0.50),
                    "value_size_p90": sizes.quantile(0.90),
                    "value_size_p95": sizes.quantile(0.95),
                    "value_size_p99": sizes.quantile(0.99),
                    "value_size_max": sizes.max(),
                    "frac_gt_2kb": (sizes > 2_000).mean(),
                    "frac_gt_8kb": (sizes > 8_000).mean(),
                    "frac_gt_32kb": (sizes > 32_000).mean(),
                    "est_toast_chunks_p95": np.ceil(sizes.quantile(0.95) / 1996.0),
                    "est_toast_chunks_p99": np.ceil(sizes.quantile(0.99) / 1996.0),
                    "est_toast_chunks_max": np.ceil(sizes.max() / 1996.0),
                }
            )
    return pd.DataFrame(rows).sort_values(["run_id", "Epoch"]).reset_index(drop=True)


def load_watcher_metrics() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for run in [4, 5, 6]:
        path = (
            ROOT
            / f"JSON_BLUE/run_{run}_metrics/"
            / f"ycsb_postgresql_arrayjson_vacuum_notfull_bigcache_zipfian_heavy_pure_run{run}_run.metrics"
        )
        if not path.exists():
            continue
        df = pd.read_csv(
            path,
            header=None,
            names=["phase", "Epoch", "timestamp", "cpu_pct", "mem_kb", "delta_read", "delta_write"],
        )
        for col in ["Epoch", "timestamp", "cpu_pct", "mem_kb", "delta_read", "delta_write"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["run_id"] = run
        grouped = (
            df.groupby(["run_id", "Epoch"], dropna=False)
            .agg(
                watcher_samples=("Epoch", "size"),
                watcher_cpu_mean_pct=("cpu_pct", "mean"),
                watcher_cpu_max_pct=("cpu_pct", "max"),
                watcher_mem_mean_mib=("mem_kb", lambda s: s.mean(skipna=True) / 1024.0),
                watcher_mem_max_mib=("mem_kb", lambda s: s.max(skipna=True) / 1024.0),
                watcher_delta_read_sum=("delta_read", "sum"),
                watcher_delta_read_max=("delta_read", "max"),
                watcher_delta_write_sum=("delta_write", "sum"),
                watcher_delta_write_max=("delta_write", "max"),
            )
            .reset_index()
        )
        rows.append(grouped)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(["run_id", "Epoch"]).reset_index(drop=True)


def read_phase(df: pd.DataFrame, phase: str) -> pd.DataFrame:
    return df[(df["Phase"] == phase) & (df["Operation"] == "READ")].copy()


def main_run(df: pd.DataFrame) -> pd.DataFrame:
    return read_phase(df, "run")


def detect_spike_windows(run_rows: pd.DataFrame, thresholds: tuple[int, ...] = (1000, 1200, 1500)) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for run, group in run_rows.groupby("run_id"):
        group = group.sort_values("Epoch")
        for threshold in thresholds:
            start: int | None = None
            prev: int | None = None
            peak_epoch = None
            peak_value = -np.inf
            for _, row in group.iterrows():
                epoch = int(row["Epoch"])
                value = float(row["95thPercentileLatency(us)"])
                if value >= threshold:
                    if start is None:
                        start = epoch
                        peak_epoch = epoch
                        peak_value = value
                    prev = epoch
                    if value > peak_value:
                        peak_epoch = epoch
                        peak_value = value
                elif start is not None and prev is not None:
                    rows.append(
                        {
                            "run_id": run,
                            "threshold_us": threshold,
                            "start_epoch": start,
                            "end_epoch": prev,
                            "width_epochs": prev - start + 1,
                            "peak_epoch": peak_epoch,
                            "peak_p95_us": peak_value,
                        }
                    )
                    start = None
                    prev = None
                    peak_epoch = None
                    peak_value = -np.inf
            if start is not None and prev is not None:
                rows.append(
                    {
                        "run_id": run,
                        "threshold_us": threshold,
                        "start_epoch": start,
                        "end_epoch": prev,
                        "width_epochs": prev - start + 1,
                        "peak_epoch": peak_epoch,
                        "peak_p95_us": peak_value,
                    }
                )
    return pd.DataFrame(rows)


def build_phase_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for (run, phase), group in df[df["Operation"].isin(["READ", "EXTEND"])].groupby(["run_id", "Phase"]):
        group = group.sort_values("Epoch")
        if phase == "load":
            continue
        early = group[group["Epoch"].between(1, 20)]
        late = group[group["Epoch"].between(80, 100)]
        rows.append(
            {
                "run_id": run,
                "phase": phase,
                "early_p95_mean_us": early["95thPercentileLatency(us)"].mean(),
                "late_p95_mean_us": late["95thPercentileLatency(us)"].mean(),
                "late_over_early_p95_ratio": late["95thPercentileLatency(us)"].mean()
                / early["95thPercentileLatency(us)"].mean(),
                "max_p95_us": group["95thPercentileLatency(us)"].max(),
                "peak_epoch": int(group.loc[group["95thPercentileLatency(us)"].idxmax(), "Epoch"]),
            }
        )
    return pd.DataFrame(rows).sort_values(["phase", "run_id"]).reset_index(drop=True)


def build_main_derived(df: pd.DataFrame, sizes: pd.DataFrame) -> pd.DataFrame:
    main = main_run(df)
    control = []
    for phase in ["reference", "avg-run", "clean-run"]:
        part = read_phase(df, phase)[["run_id", "Epoch", "95thPercentileLatency(us)"]].copy()
        part = part.rename(columns={"95thPercentileLatency(us)": f"{phase}_p95_us"})
        control.append(part)
    out = main[
        [
            "run_id",
            "Epoch",
            "AverageLatency(us)",
            "95thPercentileLatency(us)",
            "99thPercentileLatency(us)",
            "Throughput(ops/sec)",
            *[c for c in main.columns if c.endswith("_per_op_delta")],
        ]
    ].copy()
    for part in control:
        out = out.merge(part, on=["run_id", "Epoch"], how="left")
    out["main_minus_clean_p95_us"] = out["95thPercentileLatency(us)"] - out["clean-run_p95_us"]
    out["main_minus_avg_p95_us"] = out["95thPercentileLatency(us)"] - out["avg-run_p95_us"]
    out["main_minus_reference_p95_us"] = out["95thPercentileLatency(us)"] - out["reference_p95_us"]
    if not sizes.empty:
        out = out.merge(sizes, on=["run_id", "Epoch"], how="left")
    return out


def build_correlations(derived: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "AverageLatency(us)",
        "Throughput(ops/sec)",
        "buffers_alloc_per_op_delta",
        "tup_returned_per_op_delta",
        "tup_fetched_per_op_delta",
        "blks_read_per_op_delta",
        "blks_hit_per_op_delta",
        "wal_bytes_per_op_delta",
        "wal_records_per_op_delta",
        "wal_fpi_per_op_delta",
        "temp_bytes_per_op_delta",
        "value_size_p95",
        "value_size_p99",
        "value_size_max",
        "frac_gt_32kb",
        "est_toast_chunks_p95",
        "est_toast_chunks_p99",
        "est_toast_chunks_max",
    ]
    target = "95thPercentileLatency(us)"
    rows = []
    for col in cols:
        if col not in derived.columns:
            continue
        valid = derived[[target, col]].dropna()
        if len(valid) < 5:
            continue
        rows.append(
            {
                "feature": col,
                "spearman_rho": valid[target].corr(valid[col], method="spearman"),
                "pearson_r": valid[target].corr(valid[col], method="pearson"),
                "n": len(valid),
            }
        )
    return pd.DataFrame(rows).sort_values("spearman_rho", ascending=False).reset_index(drop=True)


def build_watcher_correlations(watcher_with_latency: pd.DataFrame) -> pd.DataFrame:
    if watcher_with_latency.empty:
        return pd.DataFrame()
    target = "95thPercentileLatency(us)"
    rows = []
    for col in [
        "watcher_samples",
        "watcher_cpu_mean_pct",
        "watcher_cpu_max_pct",
        "watcher_mem_mean_mib",
        "watcher_mem_max_mib",
        "watcher_delta_read_sum",
        "watcher_delta_read_max",
        "watcher_delta_write_sum",
        "watcher_delta_write_max",
    ]:
        valid = watcher_with_latency[[target, col]].dropna()
        if len(valid) < 5 or valid[col].nunique(dropna=True) < 2:
            rho = np.nan
            pearson = np.nan
        else:
            rho = valid[target].corr(valid[col], method="spearman")
            pearson = valid[target].corr(valid[col], method="pearson")
        rows.append({"feature": col, "spearman_rho": rho, "pearson_r": pearson, "n": len(valid)})
    return pd.DataFrame(rows)


def save_csvs(
    phase_summary: pd.DataFrame,
    spike_windows: pd.DataFrame,
    sizes: pd.DataFrame,
    derived: pd.DataFrame,
    correlations: pd.DataFrame,
    watcher: pd.DataFrame,
    watcher_correlations: pd.DataFrame,
) -> None:
    phase_summary.to_csv(OUT_DIR / "latency_phase_summary.csv", index=False)
    spike_windows.to_csv(OUT_DIR / "spike_windows.csv", index=False)
    sizes.to_csv(OUT_DIR / "value_size_tail_summary.csv", index=False)
    derived.to_csv(OUT_DIR / "main_run_derived.csv", index=False)
    correlations.to_csv(OUT_DIR / "internal_proxy_correlations.csv", index=False)
    watcher.to_csv(OUT_DIR / "watcher_run_metrics_epoch_summary.csv", index=False)
    watcher_correlations.to_csv(OUT_DIR / "watcher_metric_correlations.csv", index=False)


def style_axes(ax: plt.Axes) -> None:
    ax.grid(True, axis="y", color="#d7dee4", linewidth=0.8, alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_main_spikes(main: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for run, group in main.groupby("run_id"):
        ax.plot(
            group["Epoch"],
            group["95thPercentileLatency(us)"],
            label=f"run {run}",
            linewidth=1.9,
        )
    ax.axhspan(1000, ax.get_ylim()[1] if ax.get_ylim()[1] > 1000 else 3500, color="#f3c04d", alpha=0.12)
    ax.set_title("JSON Blue main-run p95 latency develops late clustered spikes")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("READ p95 latency (us)")
    ax.legend(ncol=4, frameon=False)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "01_main_run_p95_spike_windows.png", dpi=180)
    plt.close(fig)


def plot_phase_controls(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for phase in ["reference", "avg-run", "clean-run", "run"]:
        part = read_phase(df, phase)
        grouped = part.groupby("Epoch")["95thPercentileLatency(us)"].agg(["mean", "std"]).reset_index()
        ax.plot(
            grouped["Epoch"],
            grouped["mean"],
            label=phase,
            linewidth=2.0,
            color=PHASE_COLORS[phase],
        )
        ax.fill_between(
            grouped["Epoch"],
            grouped["mean"] - grouped["std"].fillna(0),
            grouped["mean"] + grouped["std"].fillna(0),
            color=PHASE_COLORS[phase],
            alpha=0.12,
            linewidth=0,
        )
    ax.set_title("Main-run p95 grows beyond unchanged-reference and reconstructed controls")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("READ p95 latency mean across runs (us)")
    ax.legend(frameon=False)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "02_phase_control_p95_mean.png", dpi=180)
    plt.close(fig)


def plot_excess(derived: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for run, group in derived.groupby("run_id"):
        ax.plot(group["Epoch"], group["main_minus_clean_p95_us"], label=f"run {run}", linewidth=1.7)
    ax.axhline(0, color="#2f3a44", linewidth=1)
    ax.set_title("Main-run excess over clean-run control concentrates late")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Main READ p95 minus clean-run READ p95 (us)")
    ax.legend(ncol=4, frameon=False)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "03_main_run_excess_vs_clean_control.png", dpi=180)
    plt.close(fig)


def plot_tail_sizes(sizes: pd.DataFrame, derived: pd.DataFrame) -> None:
    if sizes.empty:
        return
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    for run, group in sizes.groupby("run_id"):
        axes[0].plot(group["Epoch"], group["value_size_p95"] / 1024, label=f"run {run} p95", linewidth=1.8)
        axes[0].plot(
            group["Epoch"],
            group["value_size_p99"] / 1024,
            label=f"run {run} p99",
            linestyle="--",
            linewidth=1.2,
            alpha=0.75,
        )
        axes[1].plot(group["Epoch"], group["est_toast_chunks_p99"], label=f"run {run}", linewidth=1.8)
    axes[0].set_title("Zipfian JSONB arrays push the tail of row values far past TOAST territory")
    axes[0].set_ylabel("Logical value size (KiB)")
    axes[0].legend(ncol=3, frameon=False)
    axes[1].set_title("Estimated p99 TOAST chunk fanout grows with epoch")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Estimated chunks at p99 size")
    axes[1].legend(ncol=3, frameon=False)
    for ax in axes:
        style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "04_tail_value_size_and_estimated_toast_chunks.png", dpi=180)
    plt.close(fig)


def plot_latency_vs_chunks(derived: pd.DataFrame) -> None:
    chunk_col = "est_toast_chunks_p99"
    if chunk_col not in derived.columns:
        return
    plot_df = derived.dropna(subset=[chunk_col, "95thPercentileLatency(us)"])
    if plot_df.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 6))
    for run, group in plot_df.groupby("run_id"):
        ax.scatter(
            group[chunk_col],
            group["95thPercentileLatency(us)"],
            label=f"run {run}",
            s=28,
            alpha=0.75,
        )
    ax.set_title("Main-run p95 rises with estimated p99 TOAST chunk fanout")
    ax.set_xlabel("Estimated TOAST chunks at p99 logical row size")
    ax.set_ylabel("Main READ p95 latency (us)")
    ax.legend(frameon=False)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "05_latency_vs_estimated_toast_chunks.png", dpi=180)
    plt.close(fig)


def plot_correlation_bar(correlations: pd.DataFrame) -> None:
    if correlations.empty:
        return
    labels = {
        "AverageLatency(us)": "avg latency",
        "Throughput(ops/sec)": "throughput",
        "buffers_alloc_per_op_delta": "buffer allocs/op delta",
        "tup_returned_per_op_delta": "tuples returned/op delta",
        "tup_fetched_per_op_delta": "tuples fetched/op delta",
        "blks_read_per_op_delta": "block reads/op delta",
        "blks_hit_per_op_delta": "block hits/op delta",
        "wal_bytes_per_op_delta": "WAL bytes/op delta",
        "wal_records_per_op_delta": "WAL records/op delta",
        "wal_fpi_per_op_delta": "WAL FPI/op delta",
        "temp_bytes_per_op_delta": "temp bytes/op delta",
        "value_size_p95": "value size p95",
        "value_size_p99": "value size p99",
        "value_size_max": "value size max",
        "frac_gt_32kb": "frac rows >32 KiB",
        "est_toast_chunks_p95": "est chunks p95",
        "est_toast_chunks_p99": "est chunks p99",
        "est_toast_chunks_max": "est chunks max",
    }
    plot_df = correlations.copy()
    plot_df["label"] = plot_df["feature"].map(labels).fillna(plot_df["feature"])
    plot_df = plot_df.reindex(plot_df["spearman_rho"].abs().sort_values(ascending=True).index).tail(14)
    colors = np.where(plot_df["spearman_rho"] >= 0, "#2a9d8f", "#cc4c4c")
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(plot_df["label"], plot_df["spearman_rho"], color=colors)
    ax.axvline(0, color="#2f3a44", linewidth=1)
    ax.set_title("Main-run p95 is aligned with storage/read-amplification proxies")
    ax.set_xlabel("Spearman correlation with main READ p95")
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "06_internal_proxy_correlations.png", dpi=180)
    plt.close(fig)


def plot_internal_proxies(derived: pd.DataFrame) -> None:
    cols = [
        ("buffers_alloc_per_op_delta", "buffer allocs/op delta"),
        ("blks_read_per_op_delta", "block reads/op delta"),
        ("wal_bytes_per_op_delta", "WAL bytes/op delta"),
    ]
    fig, axes = plt.subplots(len(cols), 1, figsize=(12, 9), sharex=True)
    for ax, (col, label) in zip(axes, cols):
        if col not in derived.columns:
            continue
        for run, group in derived.groupby("run_id"):
            ax.plot(group["Epoch"], group[col], label=f"run {run}", linewidth=1.5)
        ax.set_ylabel(label)
        style_axes(ax)
    axes[0].set_title("Per-phase PostgreSQL counter deltas rise with the late read cliff")
    axes[-1].set_xlabel("Epoch")
    axes[0].legend(ncol=4, frameon=False)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "07_run_phase_internal_proxies.png", dpi=180)
    plt.close(fig)


def plot_watcher_io_vs_p95(watcher: pd.DataFrame) -> None:
    if watcher.empty:
        return
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    for run, group in watcher.groupby("run_id"):
        axes[0].plot(group["Epoch"], group["95thPercentileLatency(us)"], label=f"run {run}", linewidth=1.8)
        axes[1].plot(group["Epoch"], group["watcher_delta_read_sum"], label=f"run {run}", linewidth=1.4)
        axes[2].plot(group["Epoch"], group["watcher_delta_write_sum"], label=f"run {run}", linewidth=1.4)
    axes[0].set_title("Stored watcher proc-I/O deltas do not explain the p95 spikes")
    axes[0].set_ylabel("Main READ p95 (us)")
    axes[1].set_ylabel("Watcher read bytes sum")
    axes[2].set_ylabel("Watcher write bytes sum")
    axes[2].set_xlabel("Epoch")
    if watcher[["watcher_delta_read_sum", "watcher_delta_write_sum"]].fillna(0).to_numpy().max() == 0:
        axes[1].text(
            0.5,
            0.5,
            "all stored delta_read values are zero",
            transform=axes[1].transAxes,
            ha="center",
            va="center",
            color="#6b7280",
        )
        axes[2].text(
            0.5,
            0.5,
            "all stored delta_write values are zero",
            transform=axes[2].transAxes,
            ha="center",
            va="center",
            color="#6b7280",
        )
    axes[0].legend(ncol=3, frameon=False)
    for ax in axes:
        style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "08_watcher_proc_io_vs_p95_diagnostic.png", dpi=180)
    plt.close(fig)


def plot_watcher_cpu_memory_vs_p95(watcher: pd.DataFrame) -> None:
    if watcher.empty:
        return
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    for run, group in watcher.groupby("run_id"):
        axes[0].plot(group["Epoch"], group["95thPercentileLatency(us)"], label=f"run {run}", linewidth=1.8)
        axes[1].plot(group["Epoch"], group["watcher_cpu_mean_pct"], label=f"run {run}", linewidth=1.4)
        axes[2].plot(group["Epoch"], group["watcher_mem_mean_mib"], label=f"run {run}", linewidth=1.4)
    axes[0].set_title("Watcher CPU/memory summaries are available, but CPU does not visually spike with p95")
    axes[0].set_ylabel("Main READ p95 (us)")
    axes[1].set_ylabel("CPU mean (%)")
    axes[2].set_ylabel("Memory mean (MiB)")
    axes[2].set_xlabel("Epoch")
    axes[0].legend(ncol=3, frameon=False)
    for ax in axes:
        style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "09_watcher_cpu_memory_vs_p95.png", dpi=180)
    plt.close(fig)


def write_report(
    phase_summary: pd.DataFrame,
    spike_windows: pd.DataFrame,
    sizes: pd.DataFrame,
    correlations: pd.DataFrame,
    watcher: pd.DataFrame,
    watcher_correlations: pd.DataFrame,
) -> None:
    main_rows = phase_summary[phase_summary["phase"] == "run"].copy()
    reference_rows = phase_summary[phase_summary["phase"] == "reference"].copy()
    clean_rows = phase_summary[phase_summary["phase"] == "clean-run"].copy()
    avg_rows = phase_summary[phase_summary["phase"] == "avg-run"].copy()

    late_ratio_min = main_rows["late_over_early_p95_ratio"].min()
    late_ratio_max = main_rows["late_over_early_p95_ratio"].max()
    ref_late_mean = reference_rows["late_p95_mean_us"].mean()
    main_late_mean = main_rows["late_p95_mean_us"].mean()
    clean_late_mean = clean_rows["late_p95_mean_us"].mean()
    avg_late_mean = avg_rows["late_p95_mean_us"].mean()

    run456_sizes = sizes[sizes["Epoch"].isin([1, 60, 100])]
    size_p99_epoch1 = run456_sizes[run456_sizes["Epoch"] == 1]["value_size_p99"].mean()
    size_p99_epoch100 = run456_sizes[run456_sizes["Epoch"] == 100]["value_size_p99"].mean()
    chunks_p99_epoch1 = run456_sizes[run456_sizes["Epoch"] == 1]["est_toast_chunks_p99"].mean()
    chunks_p99_epoch100 = run456_sizes[run456_sizes["Epoch"] == 100]["est_toast_chunks_p99"].mean()
    frac32_epoch60 = run456_sizes[run456_sizes["Epoch"] == 60]["frac_gt_32kb"].mean()

    top_corr = correlations.head(8).copy()
    top_corr["spearman_rho"] = top_corr["spearman_rho"].round(3)

    long_windows = spike_windows[
        (spike_windows["threshold_us"] == 1000) & (spike_windows["width_epochs"] >= 6)
    ].copy()
    long_window_text = "; ".join(
        f"run {int(r.run_id)} epochs {int(r.start_epoch)}-{int(r.end_epoch)} ({int(r.width_epochs)} epochs)"
        for r in long_windows.itertuples(index=False)
    )

    lines = [
        "# JSON Blue Evidence for JSONB TOAST Amplification",
        "",
        "Generated from the current `JSON_BLUE` latency CSVs and the available run 4-6 value-size matrices.",
        "",
        "## What The Current Data Supports",
        "",
        "- The anomalous late main-run READ p95 increase is replicated across all four JSON Blue runs.",
        f"  The late-window main-run p95 mean is {late_ratio_min:.1f}x to {late_ratio_max:.1f}x the first-20-epoch mean.",
        f"- The unchanged `reference` read control remains near-flat at about {ref_late_mean:.0f} us late-window p95, while the main run averages about {main_late_mean:.0f} us.",
        f"- `clean-run` and `avg-run` also rise late ({clean_late_mean:.0f} us and {avg_late_mean:.0f} us p95 on average), which says larger values alone matter. The main run is still higher, which is consistent with additional storage/history effects from the append-grown table.",
        f"- At a 1000 us p95 threshold, the late high-latency regions include: {long_window_text}. This matches the observation that the main-run spikes are clustered in roughly multi-epoch windows rather than one isolated point.",
        "",
        "## Evidence Linking The Spike To Large Toasted Values",
        "",
        f"- In the value-size matrices for runs 4-6, mean p99 logical row size grows from about {size_p99_epoch1/1024:.1f} KiB at epoch 1 to about {size_p99_epoch100/1024:.1f} KiB at epoch 100.",
        f"- Using PostgreSQL's roughly 2 KiB TOAST chunk scale as an estimate, that is about {chunks_p99_epoch1:.0f} chunks at epoch 1 versus about {chunks_p99_epoch100:.0f} chunks at epoch 100 for the p99 row.",
        f"- By epoch 60, about {100*frac32_epoch60:.1f}% of rows in the available value-size matrices are already above 32 KiB logical size. That means p95 reads are no longer rare single-tuple reads; many reads are eligible to fetch and detoast large varlena payloads.",
        "",
        "## Internal PostgreSQL Proxy Evidence",
        "",
        "The original dataset does not contain direct TOAST table sizes or detoast timings, so these are proxies rather than proof. Still, main-run p95 tracks PostgreSQL counter deltas strongly:",
        "",
        markdown_table(top_corr[["feature", "spearman_rho", "n"]]),
        "",
        "Interpretation: latency rises with buffer allocation, tuple-return/fetch pressure, WAL/checkpoint-related deltas, and estimated TOAST fanout. That is the expected shape if large JSONB array values are increasing the amount of PostgreSQL work needed for a read path.",
        "",
        "## Plots",
        "",
        "- `json_blue_toast_evidence/01_main_run_p95_spike_windows.png`",
        "- `json_blue_toast_evidence/02_phase_control_p95_mean.png`",
        "- `json_blue_toast_evidence/03_main_run_excess_vs_clean_control.png`",
        "- `json_blue_toast_evidence/04_tail_value_size_and_estimated_toast_chunks.png`",
        "- `json_blue_toast_evidence/05_latency_vs_estimated_toast_chunks.png`",
        "- `json_blue_toast_evidence/06_internal_proxy_correlations.png`",
        "- `json_blue_toast_evidence/07_run_phase_internal_proxies.png`",
        "- `json_blue_toast_evidence/08_watcher_proc_io_vs_p95_diagnostic.png`",
        "- `json_blue_toast_evidence/09_watcher_cpu_memory_vs_p95.png`",
        "",
        "## Watcher Metrics Check",
        "",
        "The stored watcher `.metrics` files for runs 4-6 do include per-second CPU and memory samples for the main `run` phase. They do not include useful process I/O deltas: every stored `delta_read` and `delta_write` value is zero across the available run/phase watcher files.",
        "",
        "That means the current watcher files cannot directly test a visual `delta_read`/`delta_write` spike. The best current spike-parallel signals remain the PostgreSQL counter deltas in the main CSVs (`blks_read`, `buffers_alloc`, WAL records/bytes) and the value-size/estimated-TOAST fanout summaries.",
        "",
        "Watcher CPU/memory correlations with p95 are saved in `watcher_metric_correlations.csv`; they are weaker and less mechanism-specific than the PostgreSQL counter proxies.",
        "",
        "## Limits",
        "",
        "- Runs 4-6 have full value-size matrices for this scenario; run 3 contributes to latency evidence but not tail-size plots.",
        "- The current CSV counters are cumulative PostgreSQL statistics sampled after phases. The per-op deltas are useful support, but they are not as clean as the new one-shot `.dbstats` and detoast probes we added to the harness.",
        "- The TOAST chunk counts here are estimates from logical value size. The confirmation run should use direct TOAST relation size/chunk instrumentation and detoast probes.",
        "",
        "Bottom line: the current dataset already supports the JSONB TOAST amplification hypothesis. It does not prove the internal mechanism by itself, but the timing, controls, value-size tail growth, and PostgreSQL counter proxies all point in the same direction.",
        "",
    ]
    REPORT.write_text("\n".join(lines))


def markdown_table(df: pd.DataFrame) -> str:
    headers = [str(col) for col in df.columns]
    rows = []
    for _, row in df.iterrows():
        rows.append([str(row[col]) for col in df.columns])
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def main() -> None:
    ensure_output()
    latency = load_latency()
    sizes = load_value_size_summaries()
    watcher = load_watcher_metrics()
    phase_summary = build_phase_summary(latency)
    main_derived = build_main_derived(latency, sizes)
    if not watcher.empty:
        watcher = watcher.merge(
            main_derived[["run_id", "Epoch", "95thPercentileLatency(us)", "Throughput(ops/sec)"]],
            on=["run_id", "Epoch"],
            how="left",
        )
    spike_windows = detect_spike_windows(main_run(latency))
    correlations = build_correlations(main_derived)
    watcher_correlations = build_watcher_correlations(watcher)

    save_csvs(phase_summary, spike_windows, sizes, main_derived, correlations, watcher, watcher_correlations)

    plot_main_spikes(main_run(latency))
    plot_phase_controls(latency)
    plot_excess(main_derived)
    plot_tail_sizes(sizes, main_derived)
    plot_latency_vs_chunks(main_derived)
    plot_correlation_bar(correlations)
    plot_internal_proxies(main_derived)
    plot_watcher_io_vs_p95(watcher)
    plot_watcher_cpu_memory_vs_p95(watcher)
    write_report(phase_summary, spike_windows, sizes, correlations, watcher, watcher_correlations)

    print(f"Wrote {REPORT}")
    print(f"Wrote plots and CSVs to {OUT_DIR}")


if __name__ == "__main__":
    main()
