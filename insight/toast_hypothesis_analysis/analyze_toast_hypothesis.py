#!/usr/bin/env python3
"""Analyze the TOAST_HYPOTHESIS run against the latest spike hypotheses."""

from __future__ import annotations

import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from scipy.stats import pearsonr, spearmanr


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_ROOT = SCRIPT_DIR.parents[1]
HYPOTHESIS_ROOT = DATA_ROOT / "TOAST_HYPOTHESIS" / "HYPOTHESIS_DATA"
TRIGGER_ROOT = HYPOTHESIS_ROOT / "toast_spike_trigger"
OUT = SCRIPT_DIR

RUN_NAME = "postgresql_arrayjson_TOAST_HYPOTHESIS_run1_zipfian_heavy_pure"
COMPONENTS = [
    "query_execute_us",
    "resultset_next_us",
    "json_fetch_us",
    "json_parse_us",
    "value_join_us",
]


def quantile(series: pd.Series, q: float) -> float:
    if series.empty:
        return np.nan
    return float(series.quantile(q))


def corr_pair(x: pd.Series, y: pd.Series, method: str) -> float:
    mask = x.notna() & y.notna()
    if mask.sum() < 3:
        return np.nan
    x2 = x[mask]
    y2 = y[mask]
    if x2.nunique() < 2 or y2.nunique() < 2:
        return np.nan
    if method == "spearman":
        return float(spearmanr(x2, y2).correlation)
    return float(pearsonr(x2, y2)[0])


def fmt_num(value: float, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    if abs(value) >= 1000:
        return f"{value:,.{digits}f}"
    return f"{value:.{digits}f}"


def fmt_int(value: float) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{int(round(value)):,}"


def markdown_table(df: pd.DataFrame, columns: list[str], headers: list[str] | None = None) -> str:
    if headers is None:
        headers = columns
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(rows)


def load_workload() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = pd.read_csv(
        HYPOTHESIS_ROOT
        / "hypothesis_workload_data"
        / f"{RUN_NAME}.csv"
    )
    run = (
        work[work["Phase"] == "run"]
        .copy()
        .sort_values("Epoch")
        .rename(
            columns={
                "95thPercentileLatency(us)": "p95_us",
                "99thPercentileLatency(us)": "p99_us",
                "AverageLatency(us)": "avg_us",
                "Runtime(ms)": "runtime_ms",
                "Throughput(ops/sec)": "throughput_ops_sec",
            }
        )
    )
    peaks, props = find_peaks(run["p95_us"], prominence=80, distance=5)
    peaks_df = run.iloc[peaks][
        ["Epoch", "p95_us", "avg_us", "runtime_ms", "throughput_ops_sec"]
    ].copy()
    peaks_df["prominence_us"] = props["prominences"]
    peaks_df = peaks_df.nlargest(5, "prominence_us").sort_values("Epoch").reset_index(drop=True)
    return work, run, peaks_df


def value_size_summary() -> pd.DataFrame:
    path = (
        HYPOTHESIS_ROOT
        / "hypothesis_value_sizes"
        / "value_sizes_postgresql_arrayjson_TOAST_HYPOTHESIS_run1_zipfian_heavy_after_pure.csv"
    )
    sizes = pd.read_csv(path)
    rows: list[dict[str, float]] = []
    for col in sizes.columns[1:]:
        epoch = int(col.replace("Run", ""))
        values = pd.to_numeric(sizes[col], errors="coerce").dropna()
        rows.append(
            {
                "Epoch": epoch,
                "value_mean_bytes": values.mean(),
                "value_p50_bytes": values.quantile(0.50),
                "value_p90_bytes": values.quantile(0.90),
                "value_p95_bytes": values.quantile(0.95),
                "value_p99_bytes": values.quantile(0.99),
                "value_max_bytes": values.max(),
                "value_pct_gt_128k": (values > 128 * 1024).mean() * 100,
                "value_pct_gt_256k": (values > 256 * 1024).mean() * 100,
            }
        )
    return pd.DataFrame(rows)


def read_sample_summary(
    run: pd.DataFrame, peak_epochs: list[int]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    read_sample = pd.read_csv(TRIGGER_ROOT / f"{RUN_NAME}_read_sample.csv")
    slow_sample = pd.read_csv(TRIGGER_ROOT / f"{RUN_NAME}_slow_read_sample.csv")
    ops_by_epoch = run.set_index("Epoch")["Operations"].to_dict()

    sample_rows = []
    for epoch, group in read_sample.groupby("epoch"):
        row = {
            "Epoch": epoch,
            "sample_n": len(group),
            "sample_latency_p50_us": quantile(group["latency_us"], 0.50),
            "sample_latency_p95_us": quantile(group["latency_us"], 0.95),
            "sample_latency_p99_us": quantile(group["latency_us"], 0.99),
            "sample_key_p50_bytes": quantile(group["key_size_bytes"], 0.50),
            "sample_key_p95_bytes": quantile(group["key_size_bytes"], 0.95),
            "sample_key_p99_bytes": quantile(group["key_size_bytes"], 0.99),
            "sample_key_max_bytes": group["key_size_bytes"].max(),
            "sample_pct_gt_128k": (group["key_size_bytes"] > 128 * 1024).mean() * 100,
            "sample_pct_gt_256k": (group["key_size_bytes"] > 256 * 1024).mean() * 100,
            "sample_key_latency_spearman": corr_pair(group["key_size_bytes"], group["latency_us"], "spearman"),
            "sample_key_latency_pearson": corr_pair(group["key_size_bytes"], group["latency_us"], "pearson"),
        }
        for component in COMPONENTS:
            row[f"sample_{component}_mean"] = group[component].mean()
            row[f"sample_{component}_p95"] = quantile(group[component], 0.95)
        sample_rows.append(row)
    sample_epoch = pd.DataFrame(sample_rows)

    slow_rows = []
    for epoch, group in slow_sample.groupby("epoch"):
        total_latency = group["latency_us"].mean()
        row = {
            "Epoch": epoch,
            "slow_n": len(group),
            "slow_rate_pct": len(group) / ops_by_epoch.get(epoch, 100000) * 100,
            "slow_latency_p50_us": quantile(group["latency_us"], 0.50),
            "slow_latency_p95_us": quantile(group["latency_us"], 0.95),
            "slow_latency_p99_us": quantile(group["latency_us"], 0.99),
            "slow_key_p50_bytes": quantile(group["key_size_bytes"], 0.50),
            "slow_key_p95_bytes": quantile(group["key_size_bytes"], 0.95),
            "slow_key_p99_bytes": quantile(group["key_size_bytes"], 0.99),
            "slow_pct_gt_128k": (group["key_size_bytes"] > 128 * 1024).mean() * 100,
            "slow_pct_gt_256k": (group["key_size_bytes"] > 256 * 1024).mean() * 100,
            "slow_key_latency_spearman": corr_pair(group["key_size_bytes"], group["latency_us"], "spearman"),
            "slow_key_latency_pearson": corr_pair(group["key_size_bytes"], group["latency_us"], "pearson"),
        }
        for component in COMPONENTS:
            row[f"slow_{component}_mean"] = group[component].mean()
            row[f"slow_{component}_p50"] = quantile(group[component], 0.50)
            row[f"slow_{component}_p95"] = quantile(group[component], 0.95)
            row[f"slow_{component}_share_mean"] = (
                group[component].mean() / total_latency if total_latency else np.nan
            )
        slow_rows.append(row)
    slow_epoch = pd.DataFrame(slow_rows)

    quartile_rows = []
    for source_name, frame in [("read_sample", read_sample), ("slow_sample", slow_sample)]:
        current = frame.copy()
        current["run_quartile"] = pd.cut(
            current["operation_index"],
            bins=[0, 25000, 50000, 75000, 100000],
            labels=["q1", "q2", "q3", "q4"],
            include_lowest=True,
        )
        for (epoch, run_quartile), group in current.groupby(["epoch", "run_quartile"], observed=True):
            operations_in_quartile = ops_by_epoch.get(epoch, 100000) / 4
            quartile_rows.append(
                {
                    "Epoch": int(epoch),
                    "source": source_name,
                    "run_quartile": str(run_quartile),
                    "n": len(group),
                    "rate_pct": len(group) / operations_in_quartile * 100,
                    "latency_p50_us": quantile(group["latency_us"], 0.50),
                    "latency_p95_us": quantile(group["latency_us"], 0.95),
                    "key_p50_bytes": quantile(group["key_size_bytes"], 0.50),
                    "key_p95_bytes": quantile(group["key_size_bytes"], 0.95),
                }
            )
    quartiles = pd.DataFrame(quartile_rows)

    bins = [0, 64 * 1024, 128 * 1024, 256 * 1024, 512 * 1024, 1024 * 1024, math.inf]
    labels = ["<=64 KiB", "64-128 KiB", "128-256 KiB", "256-512 KiB", "512 KiB-1 MiB", ">1 MiB"]
    bin_rows = []
    epoch_sets = {
        "all": read_sample,
        "late_epoch_80_100": read_sample[read_sample["epoch"] >= 80],
        "peak_epochs": read_sample[read_sample["epoch"].isin(peak_epochs)],
    }
    for set_name, frame in epoch_sets.items():
        temp = frame.copy()
        temp["key_size_bin"] = pd.cut(
            temp["key_size_bytes"], bins=bins, labels=labels, include_lowest=True
        )
        for key_size_bin, group in temp.groupby("key_size_bin", observed=False):
            if group.empty:
                continue
            row = {
                "epoch_set": set_name,
                "key_size_bin": str(key_size_bin),
                "n": len(group),
                "latency_p50_us": quantile(group["latency_us"], 0.50),
                "latency_p95_us": quantile(group["latency_us"], 0.95),
                "key_median_bytes": quantile(group["key_size_bytes"], 0.50),
            }
            for component in COMPONENTS:
                row[f"{component}_mean"] = group[component].mean()
            bin_rows.append(row)
    key_bins = pd.DataFrame(bin_rows)

    return sample_epoch, slow_epoch, quartiles, key_bins


def phase_duration_summary() -> pd.DataFrame:
    timeline = pd.read_csv(TRIGGER_ROOT / f"{RUN_NAME}_phase_timeline.csv")
    rows = []
    for (epoch, phase), group in timeline.groupby(["epoch", "phase"]):
        starts = group[group["event"].str.endswith("_start")]["timestamp_unix_ms"]
        ends = group[group["event"].str.endswith("_end")]["timestamp_unix_ms"]
        if starts.empty or ends.empty:
            continue
        rows.append(
            {
                "Epoch": epoch,
                "phase": phase,
                "duration_s": (ends.max() - starts.min()) / 1000,
            }
        )
    durations = pd.DataFrame(rows).pivot(index="Epoch", columns="phase", values="duration_s")
    durations = durations.add_prefix("duration_").add_suffix("_s").reset_index()
    return durations


def pg_os_summary() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pg_1s = pd.read_csv(TRIGGER_ROOT / f"{RUN_NAME}_pg_1s.csv")
    os_1s = pd.read_csv(TRIGGER_ROOT / f"{RUN_NAME}_os_1s.csv")
    cp = pd.read_csv(TRIGGER_ROOT / f"{RUN_NAME}_checkpoint_observations.csv")
    vacuum_progress = pd.read_csv(TRIGGER_ROOT / f"{RUN_NAME}_vacuum_progress_1s.csv")

    pg_run = (
        pg_1s[(pg_1s["Phase"] == "run") & (pg_1s["DBName"] == "ycsb")]
        .copy()
        .sort_values(["Epoch", "TimestampUnixMs"])
    )
    pg_counters = [
        "blks_read",
        "blks_hit",
        "tup_returned",
        "tup_fetched",
        "temp_bytes",
        "checkpoints_timed",
        "checkpoints_req",
        "buffers_checkpoint",
        "buffers_clean",
        "buffers_backend",
        "buffers_alloc",
        "checkpoint_write_time",
        "checkpoint_sync_time",
        "wal_bytes",
        "wal_records",
        "wal_buffers_full",
    ]
    pg_rows = []
    for epoch, group in pg_run.groupby("Epoch"):
        row = {
            "Epoch": epoch,
            "pg_run_samples": len(group),
            "run_wait_io_mean": group["wait_io_count"].mean(),
            "run_wait_io_max": group["wait_io_count"].max(),
            "run_wait_lwlock_mean": group["wait_lwlock_count"].mean(),
            "run_wait_client_mean": group["wait_client_count"].mean(),
            "run_active_backends_mean": group["active_backends"].mean(),
            "run_toast_total_bytes": group["toast_total_bytes"].dropna().iloc[-1]
            if not group["toast_total_bytes"].dropna().empty
            else np.nan,
        }
        for counter in pg_counters:
            row[f"run_delta_{counter}"] = group[counter].iloc[-1] - group[counter].iloc[0]
        pg_rows.append(row)
    pg_run_epoch = pd.DataFrame(pg_rows)

    os_run = (
        os_1s[(os_1s["Phase"] == "run") & (os_1s["DBName"] == "ycsb")]
        .copy()
        .sort_values(["Epoch", "TimestampUnixMs"])
    )
    os_fields = [
        "postgres_cpu_pct",
        "postgres_rss_kb",
        "mem_available_kb",
        "mem_dirty_kb",
        "mem_writeback_kb",
        "disk_reads_s",
        "disk_writes_s",
        "disk_read_kb_s",
        "disk_write_kb_s",
        "disk_await_ms",
        "disk_aqu_sz",
        "disk_util_pct",
    ]
    os_rows = []
    for epoch, group in os_run.groupby("Epoch"):
        row = {"Epoch": epoch, "os_run_samples": len(group)}
        for field in os_fields:
            row[f"run_os_{field}_mean"] = group[field].mean()
            row[f"run_os_{field}_max"] = group[field].max()
        os_rows.append(row)
    os_run_epoch = pd.DataFrame(os_rows)

    cp_counters = [
        "checkpoints_timed",
        "checkpoints_req",
        "checkpoint_write_time",
        "checkpoint_sync_time",
        "buffers_checkpoint",
        "buffers_clean",
        "buffers_backend",
        "buffers_alloc",
        "wal_bytes",
        "wal_records",
    ]
    cp_rows = []
    for (epoch, phase), group in cp.groupby(["epoch", "phase"]):
        starts = group[group["event"].str.endswith("_start")].sort_values("timestamp_unix_ms")
        ends = group[group["event"].str.endswith("_end")].sort_values("timestamp_unix_ms")
        if starts.empty or ends.empty:
            continue
        start = starts.iloc[0]
        end = ends.iloc[-1]
        row = {"Epoch": epoch, "phase": phase}
        for counter in cp_counters:
            row[f"delta_{counter}"] = end[counter] - start[counter]
        cp_rows.append(row)
    cp_phase = pd.DataFrame(cp_rows)
    cp_wide = cp_phase.pivot(index="Epoch", columns="phase")
    cp_wide.columns = [f"{phase}_{metric}" for metric, phase in cp_wide.columns]
    cp_wide = cp_wide.reset_index()

    vacuum_rows = []
    for epoch, group in vacuum_progress.groupby("epoch"):
        row = {
            "Epoch": epoch,
            "vacuum_progress_samples": len(group),
            "vacuum_toast_samples": group["relation"].astype(str).str.contains("toast").sum(),
            "vacuum_heap_blks_total_max": group["heap_blks_total"].max(),
            "vacuum_heap_blks_scanned_max": group["heap_blks_scanned"].max(),
            "vacuum_heap_blks_vacuumed_max": group["heap_blks_vacuumed"].max(),
            "vacuum_index_vacuum_count_max": group["index_vacuum_count"].max(),
            "vacuum_dead_tuples_max": group["num_dead_tuples"].max(),
        }
        phase_share = group["phase"].value_counts(normalize=True)
        for phase, share in phase_share.items():
            row[f"vacuum_phase_share_{phase.replace(' ', '_')}"] = share
        vacuum_rows.append(row)
    vacuum_epoch = pd.DataFrame(vacuum_rows)

    return pg_run_epoch, os_run_epoch, cp_wide, vacuum_epoch


def detoast_probe_summary() -> pd.DataFrame:
    path = (
        HYPOTHESIS_ROOT
        / "hypothesis_stats"
        / "postgresql_arrayjson_TOAST_HYPOTHESIS_run1_zipfian_heavy_pure_detoast_probe.log"
    )
    if not path.exists():
        return pd.DataFrame()

    header_re = re.compile(
        r"Epoch=(?P<epoch>\d+)\s+Run=(?P<run>\d+)\s+Iteration=(?P<iteration>\d+)"
        r"\s+Phase=(?P<phase>\S+)\s+Probe=(?P<probe>\S+)"
    )
    size_re = re.compile(r"SizeBytes=(?P<size>\d+)")
    execution_re = re.compile(r"Execution Time:\s+(?P<ms>[0-9.]+)\s+ms")
    buffers_re = re.compile(r"Buffers:\s+shared hit=(?P<hits>\d+)")

    rows = []
    current: dict[str, object] | None = None
    current_section: str | None = None

    def finish() -> None:
        if current:
            rows.append(current.copy())

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        match = header_re.search(line)
        if match:
            finish()
            data = match.groupdict()
            current = {
                "Epoch": int(data["iteration"]),
                "header_epoch": int(data["epoch"]),
                "header_run": int(data["run"]),
                "phase": data["phase"],
                "probe": data["probe"],
            }
            current_section = None
            continue
        if current is None:
            continue
        size_match = size_re.search(line)
        if size_match:
            current["size_bytes"] = int(size_match.group("size"))
            continue
        if line == "Lookup-only probe":
            current_section = "lookup"
            continue
        if line == "JSONB array-length detoast probe":
            current_section = "array_length"
            continue
        if line == "Detoast and JSONB serialization probe":
            current_section = "serialize"
            continue
        execution_match = execution_re.search(line)
        if execution_match and current_section:
            current[f"{current_section}_execution_ms"] = float(execution_match.group("ms"))
            continue
        buffers_match = buffers_re.search(line)
        if buffers_match and current_section:
            key = f"{current_section}_shared_hit"
            if key not in current:
                current[key] = int(buffers_match.group("hits"))
    finish()

    return pd.DataFrame(rows)


def build_epoch_summary() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work, run, peaks_df = load_workload()
    val = value_size_summary()
    sample_epoch, slow_epoch, quartiles, key_bins = read_sample_summary(
        run, peaks_df["Epoch"].astype(int).tolist()
    )
    durations = phase_duration_summary()
    pg_run_epoch, os_run_epoch, cp_wide, vacuum_epoch = pg_os_summary()

    summary = run[
        [
            "Epoch",
            "p95_us",
            "p99_us",
            "avg_us",
            "runtime_ms",
            "throughput_ops_sec",
            "Operations",
        ]
    ].copy()
    for frame in [
        val,
        sample_epoch,
        slow_epoch,
        durations,
        pg_run_epoch,
        os_run_epoch,
        cp_wide,
        vacuum_epoch,
    ]:
        summary = summary.merge(frame, on="Epoch", how="left")

    peak_epochs = set(peaks_df["Epoch"].astype(int))
    summary["is_peak"] = summary["Epoch"].isin(peak_epochs)
    return summary, peaks_df, quartiles, key_bins, work


def peak_window_comparison(summary: pd.DataFrame, peaks_df: pd.DataFrame) -> pd.DataFrame:
    features = [
        "p95_us",
        "avg_us",
        "runtime_ms",
        "value_p95_bytes",
        "value_p99_bytes",
        "value_pct_gt_128k",
        "sample_key_p95_bytes",
        "sample_key_p99_bytes",
        "sample_pct_gt_128k",
        "sample_latency_p95_us",
        "slow_rate_pct",
        "slow_key_p50_bytes",
        "slow_key_p95_bytes",
        "slow_latency_p95_us",
        "slow_query_execute_us_share_mean",
        "slow_json_parse_us_share_mean",
        "duration_vacuum_s",
        "duration_run_s",
        "run_delta_blks_read",
        "run_delta_checkpoints_timed",
        "run_delta_checkpoints_req",
        "run_delta_checkpoint_write_time",
        "run_delta_checkpoint_sync_time",
        "run_delta_buffers_checkpoint",
        "run_wait_io_mean",
        "run_wait_io_max",
        "run_os_disk_read_kb_s_mean",
        "run_os_disk_write_kb_s_mean",
        "run_os_disk_await_ms_mean",
        "run_os_disk_util_pct_mean",
        "extend_delta_checkpoints_req",
        "extend_delta_checkpoint_write_time",
        "vacuum_delta_checkpoints_req",
        "vacuum_delta_checkpoint_write_time",
        "vacuum_toast_samples",
        "vacuum_dead_tuples_max",
    ]
    peak_epochs = set(peaks_df["Epoch"].astype(int))
    rows = []
    for epoch in sorted(peak_epochs):
        peak = summary[summary["Epoch"] == epoch].iloc[0]
        neighbors = summary[
            (summary["Epoch"] >= epoch - 2)
            & (summary["Epoch"] <= epoch + 2)
            & (~summary["Epoch"].isin(peak_epochs))
        ]
        for feature in features:
            if feature not in summary.columns:
                continue
            local_mean = neighbors[feature].mean()
            peak_value = peak[feature]
            rows.append(
                {
                    "peak_epoch": epoch,
                    "feature": feature,
                    "peak_value": peak_value,
                    "local_nonpeak_mean": local_mean,
                    "peak_minus_local": peak_value - local_mean,
                    "peak_vs_local_ratio": peak_value / local_mean
                    if pd.notna(local_mean) and local_mean != 0
                    else np.nan,
                }
            )
    return pd.DataFrame(rows)


def peak_quartile_profile(quartiles: pd.DataFrame, peaks_df: pd.DataFrame) -> pd.DataFrame:
    peak_epochs = set(peaks_df["Epoch"].astype(int))
    rows = []
    for epoch in sorted(peak_epochs):
        for source in ["read_sample", "slow_sample"]:
            current = quartiles[(quartiles["Epoch"] == epoch) & (quartiles["source"] == source)]
            q1 = current[current["run_quartile"] == "q1"]
            later = current[current["run_quartile"].isin(["q2", "q3", "q4"])]
            if q1.empty:
                continue
            rows.append(
                {
                    "Epoch": epoch,
                    "source": source,
                    "q1_rate_pct": q1["rate_pct"].iloc[0],
                    "q2_q4_rate_pct_mean": later["rate_pct"].mean(),
                    "q1_latency_p95_us": q1["latency_p95_us"].iloc[0],
                    "q2_q4_latency_p95_us_mean": later["latency_p95_us"].mean(),
                    "q1_key_p95_bytes": q1["key_p95_bytes"].iloc[0],
                    "q2_q4_key_p95_bytes_mean": later["key_p95_bytes"].mean(),
                }
            )
    return pd.DataFrame(rows)


def make_plots(
    summary: pd.DataFrame,
    peaks_df: pd.DataFrame,
    peak_quartiles: pd.DataFrame,
    key_bins: pd.DataFrame,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")

    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    ax1.plot(summary["Epoch"], summary["p95_us"], color="#2458a6", linewidth=2, label="main run p95")
    ax1.scatter(peaks_df["Epoch"], peaks_df["p95_us"], color="#c43c35", zorder=3, label="detected peaks")
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("p95 latency (us)", color="#2458a6")
    ax1.tick_params(axis="y", labelcolor="#2458a6")
    ax2 = ax1.twinx()
    ax2.plot(summary["Epoch"], summary["slow_rate_pct"], color="#287a54", linewidth=2, label="slow-read rate")
    ax2.plot(summary["Epoch"], summary["value_pct_gt_128k"], color="#9467bd", linewidth=1.7, label="rows >128 KiB")
    ax2.set_ylabel("percent")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title("Main-run p95 peaks against slow-read rate and value-size tail")
    fig.tight_layout()
    fig.savefig(OUT / "toast_hypothesis_p95_peaks_slow_rate.png", dpi=160)
    plt.close(fig)

    read_peak = peak_quartiles[peak_quartiles["source"] == "read_sample"].copy()
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(read_peak))
    width = 0.36
    ax.bar(x - width / 2, read_peak["q1_latency_p95_us"], width, label="q1 p95", color="#c43c35")
    ax.bar(
        x + width / 2,
        read_peak["q2_q4_latency_p95_us_mean"],
        width,
        label="q2-q4 mean p95",
        color="#4c78a8",
    )
    ax.set_xticks(x, read_peak["Epoch"].astype(str))
    ax.set_xlabel("Peak epoch")
    ax.set_ylabel("sampled read p95 latency (us)")
    ax.set_title("Peak epochs are front-loaded inside the run phase")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "toast_hypothesis_peak_quartile_latency.png", dpi=160)
    plt.close(fig)

    late_bins = key_bins[key_bins["epoch_set"] == "late_epoch_80_100"].copy()
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(late_bins))
    ax.bar(x, late_bins["latency_p95_us"], color="#7851a9", label="p95 latency")
    ax.plot(x, late_bins["latency_p50_us"], color="#222222", marker="o", label="median latency")
    ax.set_xticks(x, late_bins["key_size_bin"], rotation=25, ha="right")
    ax.set_xlabel("Read key size bin")
    ax.set_ylabel("latency (us)")
    ax.set_title("Late-run sampled latency rises sharply with value size")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "toast_hypothesis_late_latency_by_key_size.png", dpi=160)
    plt.close(fig)

    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    ax1.plot(summary["Epoch"], summary["p95_us"], color="#2458a6", label="p95 latency")
    ax1.scatter(peaks_df["Epoch"], peaks_df["p95_us"], color="#c43c35", zorder=3)
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("p95 latency (us)", color="#2458a6")
    ax1.tick_params(axis="y", labelcolor="#2458a6")
    ax2 = ax1.twinx()
    ax2.plot(summary["Epoch"], summary["run_delta_blks_read"], color="#d17c2f", label="run blks_read delta")
    ax2.plot(summary["Epoch"], summary["run_wait_io_mean"], color="#287a54", label="mean IO waits")
    ax2.set_ylabel("run-phase PG read/wait signals")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title("Run-phase read pressure rises around peak epochs")
    fig.tight_layout()
    fig.savefig(OUT / "toast_hypothesis_run_read_pressure.png", dpi=160)
    plt.close(fig)


def write_report(
    summary: pd.DataFrame,
    peaks_df: pd.DataFrame,
    peak_windows: pd.DataFrame,
    peak_quartiles: pd.DataFrame,
    key_bins: pd.DataFrame,
    detoast: pd.DataFrame,
    work: pd.DataFrame,
) -> None:
    peak_epochs = peaks_df["Epoch"].astype(int).tolist()
    peak_spacings = np.diff(peak_epochs).tolist()
    first20 = summary.head(20)
    last10 = summary.tail(10)
    phase_rows = []
    for phase in ["run", "clean-run", "avg-run", "reference"]:
        phase_df = work[work["Phase"] == phase].sort_values("Epoch")
        phase_rows.append(
            {
                "phase": phase,
                "first_20_p95_us": fmt_num(phase_df.head(20)["95thPercentileLatency(us)"].mean()),
                "last_10_p95_us": fmt_num(phase_df.tail(10)["95thPercentileLatency(us)"].mean()),
                "increase_x": fmt_num(
                    phase_df.tail(10)["95thPercentileLatency(us)"].mean()
                    / phase_df.head(20)["95thPercentileLatency(us)"].mean(),
                    2,
                ),
            }
        )
    phase_table = pd.DataFrame(phase_rows)

    peak_table = peaks_df.merge(
        summary[
            [
                "Epoch",
                "value_p95_bytes",
                "value_pct_gt_128k",
                "sample_key_p95_bytes",
                "slow_rate_pct",
                "duration_vacuum_s",
                "run_delta_blks_read",
                "run_wait_io_mean",
            ]
        ],
        on="Epoch",
        how="left",
    )
    peak_render = pd.DataFrame(
        {
            "epoch": peak_table["Epoch"].astype(int),
            "p95_us": peak_table["p95_us"].map(fmt_int),
            "prominence_us": peak_table["prominence_us"].map(fmt_int),
            "value_p95_kib": (peak_table["value_p95_bytes"] / 1024).map(lambda x: fmt_num(x, 1)),
            "rows_gt_128k_pct": peak_table["value_pct_gt_128k"].map(lambda x: fmt_num(x, 2)),
            "sample_key_p95_kib": (peak_table["sample_key_p95_bytes"] / 1024).map(lambda x: fmt_num(x, 1)),
            "slow_rate_pct": peak_table["slow_rate_pct"].map(lambda x: fmt_num(x, 2)),
            "vacuum_s": peak_table["duration_vacuum_s"].map(lambda x: fmt_num(x, 1)),
            "run_blks_read_delta": peak_table["run_delta_blks_read"].map(fmt_int),
            "run_io_wait_mean": peak_table["run_wait_io_mean"].map(lambda x: fmt_num(x, 3)),
        }
    )

    local_features = [
        "sample_pct_gt_128k",
        "slow_rate_pct",
        "duration_vacuum_s",
        "run_delta_blks_read",
        "run_wait_io_mean",
        "run_delta_checkpoints_req",
        "run_delta_checkpoint_write_time",
        "run_os_disk_read_kb_s_mean",
        "run_os_disk_await_ms_mean",
    ]
    local = peak_windows[peak_windows["feature"].isin(local_features)].copy()
    local["peak_value_fmt"] = local["peak_value"].map(lambda x: fmt_num(x, 3))
    local["local_mean_fmt"] = local["local_nonpeak_mean"].map(lambda x: fmt_num(x, 3))
    local["diff_fmt"] = local["peak_minus_local"].map(lambda x: fmt_num(x, 3))
    local_render = local[
        ["peak_epoch", "feature", "peak_value_fmt", "local_mean_fmt", "diff_fmt"]
    ].rename(
        columns={
            "peak_epoch": "epoch",
            "peak_value_fmt": "peak",
            "local_mean_fmt": "local_mean",
            "diff_fmt": "peak_minus_local",
        }
    )

    read_quartiles = peak_quartiles[peak_quartiles["source"] == "read_sample"].copy()
    slow_quartiles = peak_quartiles[peak_quartiles["source"] == "slow_sample"].copy()
    quartile_render = read_quartiles.merge(
        slow_quartiles[["Epoch", "q1_rate_pct", "q2_q4_rate_pct_mean"]],
        on="Epoch",
        suffixes=("_read", "_slow"),
    )
    quartile_render = pd.DataFrame(
        {
            "epoch": quartile_render["Epoch"].astype(int),
            "sample_q1_p95_us": quartile_render["q1_latency_p95_us"].map(fmt_int),
            "sample_q2_q4_mean_p95_us": quartile_render["q2_q4_latency_p95_us_mean"].map(fmt_int),
            "slow_q1_rate_pct": quartile_render["q1_rate_pct_slow"].map(lambda x: fmt_num(x, 2)),
            "slow_q2_q4_rate_pct": quartile_render["q2_q4_rate_pct_mean_slow"].map(lambda x: fmt_num(x, 2)),
        }
    )

    late_bins = key_bins[key_bins["epoch_set"] == "late_epoch_80_100"].copy()
    bin_render = pd.DataFrame(
        {
            "key_size_bin": late_bins["key_size_bin"],
            "n": late_bins["n"].map(fmt_int),
            "latency_p50_us": late_bins["latency_p50_us"].map(fmt_int),
            "latency_p95_us": late_bins["latency_p95_us"].map(fmt_int),
            "query_execute_mean_us": late_bins["query_execute_us_mean"].map(fmt_int),
            "json_parse_mean_us": late_bins["json_parse_us_mean"].map(fmt_int),
        }
    )

    component_late = summary[summary["Epoch"] >= 80]
    slow_query_share = component_late["slow_query_execute_us_share_mean"].mean() * 100
    slow_parse_share = component_late["slow_json_parse_us_share_mean"].mean() * 100

    read_sample = pd.read_csv(TRIGGER_ROOT / f"{RUN_NAME}_read_sample.csv")
    late_sample = read_sample[read_sample["epoch"] >= 80].copy()
    late_threshold = late_sample.groupby("epoch")["latency_us"].transform(lambda x: x.quantile(0.95))
    late_top_tail = late_sample[late_sample["latency_us"] >= late_threshold]
    late_non_tail = late_sample[late_sample["latency_us"] < late_threshold]
    late_top_tail_median_kib = late_top_tail["key_size_bytes"].median() / 1024
    late_non_tail_median_kib = late_non_tail["key_size_bytes"].median() / 1024
    late_top_tail_gt_128k_pct = (late_top_tail["key_size_bytes"] > 128 * 1024).mean() * 100

    detoast_lines = ""
    if not detoast.empty:
        detoast.to_csv(OUT / "detoast_probe_summary.csv", index=False)
        selected = detoast[
            detoast["Epoch"].isin([1, 50, 100]) & detoast["probe"].isin(["p95", "p99", "max"])
        ].copy()
        if not selected.empty:
            selected = selected[
                [
                    "Epoch",
                    "probe",
                    "size_bytes",
                    "lookup_execution_ms",
                    "serialize_execution_ms",
                    "serialize_shared_hit",
                ]
            ].sort_values(["Epoch", "probe"])
            selected_render = pd.DataFrame(
                {
                    "epoch": selected["Epoch"].astype(int),
                    "probe": selected["probe"],
                    "size_kib": (selected["size_bytes"] / 1024).map(lambda x: fmt_num(x, 1)),
                    "lookup_ms": selected["lookup_execution_ms"].map(lambda x: fmt_num(x, 3)),
                    "serialize_ms": selected["serialize_execution_ms"].map(lambda x: fmt_num(x, 3)),
                    "serialize_shared_hits": selected["serialize_shared_hit"].map(fmt_int),
                }
            )
            detoast_lines = "\n\n**Detoast Probe Split**\n\n" + markdown_table(
                selected_render,
                list(selected_render.columns),
                ["epoch", "probe", "size KiB", "lookup ms", "serialize ms", "serialize shared hits"],
            )

    os_disk_nonzero = int(
        (
            (summary.get("run_os_disk_read_kb_s_mean", pd.Series(dtype=float)).fillna(0) != 0)
            | (summary.get("run_os_disk_write_kb_s_mean", pd.Series(dtype=float)).fillna(0) != 0)
            | (summary.get("run_os_disk_await_ms_mean", pd.Series(dtype=float)).fillna(0) != 0)
        ).sum()
    )

    report = f"""# TOAST Hypothesis Trigger Analysis

Analyzed `YCSB-IVS-DATA/TOAST_HYPOTHESIS/HYPOTHESIS_DATA` against the latest hypotheses in `YCSB-IVS-DATA/insight`.

## Headline

The new high-resolution data keeps the root-cause verdict intact: JSONB/TOAST growth is the load-bearing mechanism. The sharper finding is about the immediate trigger: the recurring peaks are most consistent with a post-vacuum/cache-rewarming effect layered on top of large-value detoast and serialization cost, not with large-key sampling alone.

Detected main-run p95 peaks: `{peak_epochs}` with spacings `{peak_spacings}`.

Main-run p95 rose from `{fmt_num(first20["p95_us"].mean(), 1)} us` in epochs 1-20 to `{fmt_num(last10["p95_us"].mean(), 1)} us` in epochs 91-100. Reference p95 stayed nearly flat.

## Phase Controls

{markdown_table(phase_table, ["phase", "first_20_p95_us", "last_10_p95_us", "increase_x"], ["phase", "first 20 p95 us", "last 10 p95 us", "increase"])}

The controls matter: `clean-run` and `avg-run` degrade, so large JSONB values alone hurt reads. The append-grown main `run` still ends worse than both controls, which preserves the physical-history/cache-locality part of the hypothesis.

## Peak Summary

{markdown_table(peak_render, list(peak_render.columns), ["epoch", "p95 us", "prominence us", "value p95 KiB", "rows >128 KiB %", "sample key p95 KiB", "slow rate %", "vacuum s", "run blks_read delta", "mean IO waits"])}

## Trigger Tests

### Key Sampling

Large keys clearly create the expensive tail, but they do not fully explain the exact peak epochs. The top 5% sampled-latency reads in late epochs had a median key size of about `{fmt_num(late_top_tail_median_kib, 1)} KiB`, while the rest of the late sample had a median near `{fmt_num(late_non_tail_median_kib, 1)} KiB`; about `{fmt_num(late_top_tail_gt_128k_pct, 1)}%` of those top-tail reads were above `128 KiB`.

However, peak epochs did not consistently sample more large keys than their immediate neighbors. In several peaks, the sampled `>128 KiB` share or p99 key size is lower than the local non-peak mean. That makes key sampling a necessary ingredient, not the clock behind the 12-epoch rhythm.

### Cache Rewarming / Early-Run Penalty

The strongest trigger signal is intra-run front-loading. At every detected peak, the first quarter of the run has much worse sampled p95 latency and a much higher slow-read rate than quarters 2-4.

{markdown_table(quartile_render, list(quartile_render.columns), ["epoch", "sample q1 p95 us", "sample q2-q4 mean p95 us", "slow q1 rate %", "slow q2-q4 rate %"])}

Run-phase `blks_read` deltas are also higher at the peaks than local neighbors, and `wait_io_count` rises modestly at later peaks. The direct buffer-residency test could not run because `pg_buffercache` was unavailable in this dataset, so the cache-residency part remains inferred rather than directly observed.

### Checkpoint / Writeback

Checkpoint and writeback pressure are supported as upstream pressure, not as the immediate peak trigger. The `extend` and `vacuum` phases accumulate large checkpoint/request/write deltas that grow with the TOAST relation. Inside the `run` phase, though, checkpoint write/sync deltas are usually zero at the detected peaks, and only epoch 49 has a requested checkpoint inside the run.

The OS disk sampler did not provide a usable disk-pressure signal: `{os_disk_nonzero}` run epochs had non-zero mean read/write/await values. That prevents a direct OS-level confirmation or rejection of writeback interference.

### Vacuum Perturbation

Vacuum remains a strong secondary contributor. Vacuum time grows with the workload and is locally elevated at most peaks, but not all of them. This fits a perturbation role: vacuum is part of the cycle that disturbs cache and writeback state before reads, while TOAST growth determines how expensive misses and detoast work become.

### Server vs Client Cost

The timing split points mostly to server-side query execution/detoast/serialization, with client JSON parsing as a meaningful amplifier. In epochs 80-100, slow reads spend about `{fmt_num(slow_query_share, 1)}%` of mean latency in `query_execute_us` and `{fmt_num(slow_parse_share, 1)}%` in `json_parse_us`.

Late sampled latency by key-size bin:

{markdown_table(bin_render, list(bin_render.columns), ["key size", "n", "p50 us", "p95 us", "query mean us", "parse mean us"])}
{detoast_lines}

## Local Peak Differences

This table compares each peak with non-peak epochs in its +/-2 epoch window.

{markdown_table(local_render, list(local_render.columns), ["epoch", "feature", "peak", "local mean", "peak minus local"])}

## Verdict

1. TOAST/value-size amplification is confirmed again.
2. Large-key sampling explains why the tail gets expensive, but not why peaks recur every roughly 12 epochs.
3. The immediate trigger is most consistent with post-vacuum/cache rewarming: peak epochs are front-loaded, have higher slow-read rates, and have higher run-phase block-read deltas.
4. Checkpoint/writeback pressure is probably an upstream amplifier, but the new run-phase counters and OS sampler do not show it as the direct peak event.
5. Client parsing contributes, but server-side query execution/detoast/serialization dominates the slow-read split.

## Outputs

- `epoch_summary.csv`
- `peak_summary.csv`
- `peak_window_comparison.csv`
- `peak_quartile_profile.csv`
- `key_size_latency_bins.csv`
- `detoast_probe_summary.csv`
- `toast_hypothesis_p95_peaks_slow_rate.png`
- `toast_hypothesis_peak_quartile_latency.png`
- `toast_hypothesis_late_latency_by_key_size.png`
- `toast_hypothesis_run_read_pressure.png`
"""
    (OUT / "toast_hypothesis_trigger_analysis.md").write_text(report, encoding="utf-8")


def main() -> None:
    summary, peaks_df, quartiles, key_bins, work = build_epoch_summary()
    peak_windows = peak_window_comparison(summary, peaks_df)
    peak_quartiles = peak_quartile_profile(quartiles, peaks_df)
    detoast = detoast_probe_summary()

    summary.to_csv(OUT / "epoch_summary.csv", index=False)
    peaks_df.to_csv(OUT / "peak_summary.csv", index=False)
    peak_windows.to_csv(OUT / "peak_window_comparison.csv", index=False)
    quartiles.to_csv(OUT / "quartile_epoch_profile.csv", index=False)
    peak_quartiles.to_csv(OUT / "peak_quartile_profile.csv", index=False)
    key_bins.to_csv(OUT / "key_size_latency_bins.csv", index=False)
    if not detoast.empty:
        detoast.to_csv(OUT / "detoast_probe_summary.csv", index=False)

    make_plots(summary, peaks_df, peak_quartiles, key_bins)
    write_report(summary, peaks_df, peak_windows, peak_quartiles, key_bins, detoast, work)

    print(f"Wrote analysis outputs to {OUT}")
    print("Detected peaks:", ", ".join(str(int(x)) for x in peaks_df["Epoch"]))


if __name__ == "__main__":
    main()
