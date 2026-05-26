from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WATCHER_COLUMNS = ["Phase", "Epoch", "Timestamp", "CPU", "MemoryKB", "DeltaReadBytes", "DeltaWriteBytes"]
SUPPORTED_SUFFIXES = {".csv", ".json", ".jsonl", ".parquet", ".metrics"}
LATENCY_HINTS = ("latency", "percentile")
SYSTEM_HINTS = ("cpu", "memory", "rss", "readbytes", "writebytes", "deltareadbytes", "deltawritebytes")
PG_COUNTERS = {
    "blks_read",
    "blks_hit",
    "tup_returned",
    "tup_fetched",
    "tup_inserted",
    "tup_updated",
    "tup_deleted",
    "deadlocks",
    "temp_files",
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
    "wal_fpi",
    "wal_buffers_full",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_name(name: str) -> str:
    return "".join(ch.lower() for ch in str(name) if ch.isalnum())


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NULL", "NAN", "NA", "NONE"}:
        return None
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def compact_number(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def quantile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[lower]
    weight = pos - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 4:
        return None
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_denom = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_denom = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if x_denom == 0 or y_denom == 0:
        return None
    return numerator / (x_denom * y_denom)


def looks_like_evidence_summary(data: Any) -> bool:
    return isinstance(data, dict) and "schema_version" in data and "input" in data and "latency" in data


def load_existing_summary(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() != ".json":
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if looks_like_evidence_summary(data):
        summary = dict(data)
        summary.setdefault("loaded_existing_summary_from", relpath(path))
        return summary
    return None


def read_csv_rows(path: Path, max_rows: int | None) -> tuple[list[dict[str, Any]], list[str], bool]:
    rows: list[dict[str, Any]] = []
    truncated = False
    if path.suffix.lower() == ".metrics":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for index, raw_row in enumerate(reader, start=1):
                if max_rows is not None and len(rows) >= max_rows:
                    truncated = True
                    break
                values = dict(zip(WATCHER_COLUMNS, raw_row))
                values["_row_number"] = index
                rows.append(values)
        return rows, WATCHER_COLUMNS, truncated

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            has_header = True
        if has_header:
            reader = csv.DictReader(handle)
            columns = [str(col) for col in (reader.fieldnames or [])]
            for index, row in enumerate(reader, start=2):
                if max_rows is not None and len(rows) >= max_rows:
                    truncated = True
                    break
                row["_row_number"] = index
                rows.append(dict(row))
            return rows, columns, truncated

        raw_reader = csv.reader(handle)
        first = next(raw_reader, [])
        columns = [f"col_{idx}" for idx in range(len(first))]
        if first:
            rows.append({**dict(zip(columns, first)), "_row_number": 1})
        for index, raw_row in enumerate(raw_reader, start=2):
            if max_rows is not None and len(rows) >= max_rows:
                truncated = True
                break
            rows.append({**dict(zip(columns, raw_row)), "_row_number": index})
        return rows, columns, truncated


def read_json_rows(path: Path, max_rows: int | None) -> tuple[list[dict[str, Any]], list[str], bool]:
    rows: list[dict[str, Any]] = []
    truncated = False
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle, start=1):
                if max_rows is not None and len(rows) >= max_rows:
                    truncated = True
                    break
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    value = dict(value)
                    value["_row_number"] = index
                    rows.append(value)
        columns = sorted({key for row in rows for key in row if key != "_row_number"})
        return rows, columns, truncated

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            data = data["rows"]
        elif isinstance(data.get("data"), list):
            data = data["data"]
        else:
            data = [data]
    if not isinstance(data, list):
        data = [{"value": data}]
    for index, item in enumerate(data, start=1):
        if max_rows is not None and len(rows) >= max_rows:
            truncated = True
            break
        if isinstance(item, dict):
            row = dict(item)
        else:
            row = {"value": item}
        row["_row_number"] = index
        rows.append(row)
    columns = sorted({key for row in rows for key in row if key != "_row_number"})
    return rows, columns, truncated


def read_parquet_rows(path: Path, max_rows: int | None) -> tuple[list[dict[str, Any]], list[str], bool]:
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Parquet input requires pandas plus an installed parquet engine already in the environment.") from exc

    frame = pd.read_parquet(path)
    truncated = False
    if max_rows is not None and len(frame) > max_rows:
        frame = frame.head(max_rows)
        truncated = True
    rows = frame.to_dict(orient="records")
    for index, row in enumerate(rows, start=1):
        row["_row_number"] = index
    return rows, [str(col) for col in frame.columns], truncated


def load_table(path: Path, max_rows: int | None) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".metrics"}:
        rows, columns, truncated = read_csv_rows(path, max_rows)
    elif suffix in {".json", ".jsonl"}:
        rows, columns, truncated = read_json_rows(path, max_rows)
    elif suffix == ".parquet":
        rows, columns, truncated = read_parquet_rows(path, max_rows)
    else:
        raise ValueError(f"Unsupported input format: {path}")
    return {
        "path": path,
        "format": suffix.lstrip("."),
        "sha256": sha256_file(path),
        "rows": rows,
        "columns": columns,
        "row_count": len(rows),
        "truncated": truncated,
    }


def input_files(input_path: Path, max_files: int) -> tuple[str, list[Path], bool]:
    if input_path.is_file():
        return "file", [input_path], False
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")
    files = sorted(path for path in input_path.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES)
    truncated = len(files) > max_files
    return "directory", files[:max_files], truncated


def column_by_normalized(columns: Iterable[str]) -> dict[str, str]:
    return {normalize_name(column): column for column in columns}


def get_column(columns: Iterable[str], *candidates: str) -> str | None:
    by_norm = column_by_normalized(columns)
    for candidate in candidates:
        found = by_norm.get(normalize_name(candidate))
        if found:
            return found
    return None


def detect_latency_columns(columns: Iterable[str]) -> list[str]:
    detected: list[str] = []
    for column in columns:
        normalized = normalize_name(column)
        if any(non_latency in normalized for non_latency in ("spearman", "pearson", "correlation", "corr", "rho")):
            continue
        if any(hint in normalized for hint in LATENCY_HINTS):
            detected.append(column)
    return detected


def detect_system_columns(columns: Iterable[str]) -> list[str]:
    detected: list[str] = []
    for column in columns:
        normalized = normalize_name(column)
        if any(hint in normalized for hint in SYSTEM_HINTS):
            detected.append(column)
    return detected


def detect_pg_columns(columns: Iterable[str]) -> list[str]:
    pg_by_norm = {normalize_name(name): name for name in PG_COUNTERS}
    detected = []
    for column in columns:
        if normalize_name(column) in pg_by_norm:
            detected.append(column)
    return detected


def collect_unique(tables: list[dict[str, Any]], column_name: str, limit: int = 20) -> list[Any]:
    values: list[Any] = []
    seen: set[str] = set()
    for table in tables:
        column = get_column(table["columns"], column_name)
        if not column:
            continue
        for row in table["rows"]:
            value = row.get(column)
            if value is None or value == "":
                continue
            key = str(value)
            if key in seen:
                continue
            seen.add(key)
            values.append(value)
            if len(values) >= limit:
                return values
    return values


def numeric_values(table: dict[str, Any], column: str) -> list[tuple[int, dict[str, Any], float]]:
    values: list[tuple[int, dict[str, Any], float]] = []
    for index, row in enumerate(table["rows"]):
        value = to_float(row.get(column))
        if value is not None:
            values.append((index, row, value))
    return values


def group_rows_for_spikes(table: dict[str, Any], column: str) -> dict[tuple[str, str], list[tuple[int, dict[str, Any], float]]]:
    phase_col = get_column(table["columns"], "Phase", "phase_name")
    operation_col = get_column(table["columns"], "Operation", "operation_name")
    groups: dict[tuple[str, str], list[tuple[int, dict[str, Any], float]]] = defaultdict(list)
    for item in numeric_values(table, column):
        _, row, _ = item
        phase = str(row.get(phase_col, "all")) if phase_col else "all"
        operation = str(row.get(operation_col, "all")) if operation_col else "all"
        groups[(phase, operation)].append(item)
    return groups


def spike_threshold(values: list[float]) -> float | None:
    if len(values) < 4:
        return None
    median = statistics.median(values)
    q1 = quantile(values, 0.25)
    q3 = quantile(values, 0.75)
    iqr = q3 - q1
    high_tail = quantile(values, 0.95)
    threshold = max(q3 + 1.5 * iqr, median * 1.5 if median > 0 else high_tail)
    return threshold if threshold > median else None


def cluster_candidates(
    candidates: list[tuple[int, dict[str, Any], float]],
    epoch_col: str | None,
) -> list[list[tuple[int, dict[str, Any], float]]]:
    if not candidates:
        return []
    candidates = sorted(candidates, key=lambda item: (to_float(item[1].get(epoch_col)) if epoch_col else item[0], item[0]))
    clusters: list[list[tuple[int, dict[str, Any], float]]] = [[candidates[0]]]
    previous_epoch = to_float(candidates[0][1].get(epoch_col)) if epoch_col else None
    previous_index = candidates[0][0]
    for item in candidates[1:]:
        current_epoch = to_float(item[1].get(epoch_col)) if epoch_col else None
        if current_epoch is not None and previous_epoch is not None:
            adjacent = current_epoch <= previous_epoch + 1
        else:
            adjacent = item[0] <= previous_index + 1
        if adjacent:
            clusters[-1].append(item)
        else:
            clusters.append([item])
        previous_epoch = current_epoch
        previous_index = item[0]
    return clusters


def summarize_latency(tables: list[dict[str, Any]]) -> dict[str, Any]:
    spike_windows: list[dict[str, Any]] = []
    baselines: list[dict[str, Any]] = []
    detected_metrics: set[str] = set()
    spike_index = 1

    for table in tables:
        epoch_col = get_column(table["columns"], "Epoch")
        phase_col = get_column(table["columns"], "Phase", "phase_name")
        operation_col = get_column(table["columns"], "Operation", "operation_name")
        for column in detect_latency_columns(table["columns"]):
            detected_metrics.add(column)
            all_values = [value for _, _, value in numeric_values(table, column)]
            if all_values:
                baselines.append(
                    {
                        "file": relpath(table["path"]),
                        "metric": column,
                        "n": len(all_values),
                        "median": compact_number(statistics.median(all_values)),
                        "p95": compact_number(quantile(all_values, 0.95)),
                        "max": compact_number(max(all_values)),
                    }
                )
            for (phase, operation), group in group_rows_for_spikes(table, column).items():
                values = [value for _, _, value in group]
                threshold = spike_threshold(values)
                if threshold is None:
                    continue
                candidates = [item for item in group if item[2] >= threshold and item[2] > statistics.median(values)]
                for cluster in cluster_candidates(candidates, epoch_col):
                    peak_item = max(cluster, key=lambda item: item[2])
                    epochs = [to_float(item[1].get(epoch_col)) for item in cluster] if epoch_col else []
                    epochs = [epoch for epoch in epochs if epoch is not None]
                    row_numbers = [int(item[1].get("_row_number", item[0] + 1)) for item in cluster]
                    spike_windows.append(
                        {
                            "evidence_id": f"spike_{spike_index:03d}",
                            "file": relpath(table["path"]),
                            "metric": column,
                            "phase": phase if phase_col else None,
                            "operation": operation if operation_col else None,
                            "epoch_start": compact_number(min(epochs), 0) if epochs else None,
                            "epoch_end": compact_number(max(epochs), 0) if epochs else None,
                            "row_numbers": row_numbers[:20],
                            "row_count": len(cluster),
                            "peak_value": compact_number(peak_item[2]),
                            "baseline_median": compact_number(statistics.median(values)),
                            "threshold": compact_number(threshold),
                            "severity_ratio": compact_number(peak_item[2] / statistics.median(values), 3)
                            if statistics.median(values) not in {0, 0.0}
                            else None,
                        }
                    )
                    spike_index += 1

    return {
        "metrics_detected": sorted(detected_metrics),
        "baselines": baselines[:30],
        "spike_windows": sorted(spike_windows, key=lambda item: item.get("severity_ratio") or 0, reverse=True)[:30],
    }


def summarize_system_patterns(tables: list[dict[str, Any]]) -> dict[str, Any]:
    patterns: list[dict[str, Any]] = []
    detected_metrics: set[str] = set()
    pattern_index = 1
    for table in tables:
        epoch_col = get_column(table["columns"], "Epoch")
        for column in detect_system_columns(table["columns"]):
            values = numeric_values(table, column)
            numeric = [value for _, _, value in values]
            if not numeric:
                continue
            detected_metrics.add(column)
            threshold = spike_threshold(numeric)
            peaks = [item for item in values if threshold is not None and item[2] >= threshold]
            row_numbers = [int(item[1].get("_row_number", item[0] + 1)) for item in peaks[:10]]
            epochs = [to_float(item[1].get(epoch_col)) for item in peaks] if epoch_col else []
            epochs = [epoch for epoch in epochs if epoch is not None]
            patterns.append(
                {
                    "evidence_id": f"pattern_{pattern_index:03d}",
                    "file": relpath(table["path"]),
                    "metric": column,
                    "n": len(numeric),
                    "min": compact_number(min(numeric)),
                    "mean": compact_number(statistics.fmean(numeric)),
                    "max": compact_number(max(numeric)),
                    "peak_threshold": compact_number(threshold),
                    "peak_row_numbers": row_numbers,
                    "peak_epoch_start": compact_number(min(epochs), 0) if epochs else None,
                    "peak_epoch_end": compact_number(max(epochs), 0) if epochs else None,
                }
            )
            pattern_index += 1
    return {"metrics_detected": sorted(detected_metrics), "patterns": patterns[:30]}


def grouped_counter_rows(table: dict[str, Any], column: str) -> dict[str, list[tuple[int, dict[str, Any], float]]]:
    phase_col = get_column(table["columns"], "Phase", "phase_name")
    epoch_col = get_column(table["columns"], "Epoch")
    groups: dict[str, list[tuple[int, dict[str, Any], float]]] = defaultdict(list)
    for item in numeric_values(table, column):
        _, row, _ = item
        phase = str(row.get(phase_col, "all")) if phase_col else "all"
        groups[phase].append(item)
    for key, values in groups.items():
        if epoch_col:
            values.sort(key=lambda item: (to_float(item[1].get(epoch_col)) if to_float(item[1].get(epoch_col)) is not None else item[0], item[0]))
        else:
            values.sort(key=lambda item: item[0])
        groups[key] = values
    return groups


def summarize_pg_stats(tables: list[dict[str, Any]]) -> dict[str, Any]:
    counters_detected: set[str] = set()
    counter_deltas: list[dict[str, Any]] = []
    jumps: list[dict[str, Any]] = []
    delta_index = 1
    jump_index = 1
    for table in tables:
        epoch_col = get_column(table["columns"], "Epoch")
        operation_col = get_column(table["columns"], "Operations")
        pg_columns = detect_pg_columns(table["columns"])
        counters_detected.update(pg_columns)
        for column in pg_columns:
            for phase, group in grouped_counter_rows(table, column).items():
                if len(group) < 2:
                    continue
                first = group[0][2]
                last = group[-1][2]
                delta = last - first
                operation_total = 0.0
                if operation_col:
                    for _, row, _ in group:
                        operation_total += to_float(row.get(operation_col)) or 0.0
                if abs(delta) > 0:
                    counter_deltas.append(
                        {
                            "evidence_id": f"pgdelta_{delta_index:03d}",
                            "file": relpath(table["path"]),
                            "metric": column,
                            "phase": phase,
                            "first": compact_number(first),
                            "last": compact_number(last),
                            "delta": compact_number(delta),
                            "delta_per_operation": compact_number(delta / operation_total, 8) if operation_total else None,
                            "row_numbers": [
                                int(group[0][1].get("_row_number", group[0][0] + 1)),
                                int(group[-1][1].get("_row_number", group[-1][0] + 1)),
                            ],
                        }
                    )
                    delta_index += 1

                diffs: list[tuple[int, dict[str, Any], float]] = []
                for previous, current in zip(group, group[1:]):
                    diff = current[2] - previous[2]
                    if diff != 0:
                        diffs.append((current[0], current[1], diff))
                if len(diffs) < 2:
                    continue
                diff_values = [abs(item[2]) for item in diffs]
                threshold = spike_threshold(diff_values) or quantile(diff_values, 0.95)
                for row_index, row, diff in sorted(diffs, key=lambda item: abs(item[2]), reverse=True)[:5]:
                    if abs(diff) < threshold:
                        continue
                    jumps.append(
                        {
                            "evidence_id": f"pgjump_{jump_index:03d}",
                            "file": relpath(table["path"]),
                            "metric": column,
                            "phase": phase,
                            "epoch": compact_number(to_float(row.get(epoch_col)), 0) if epoch_col else None,
                            "row_number": int(row.get("_row_number", row_index + 1)),
                            "delta": compact_number(diff),
                            "threshold": compact_number(threshold),
                        }
                    )
                    jump_index += 1

    counter_deltas.sort(key=lambda item: abs(item.get("delta") or 0), reverse=True)
    jumps.sort(key=lambda item: abs(item.get("delta") or 0), reverse=True)
    return {
        "counters_detected": sorted(counters_detected),
        "counter_deltas": counter_deltas[:40],
        "notable_counter_jumps": jumps[:40],
    }


def diff_series_by_phase(table: dict[str, Any], column: str) -> dict[int, float]:
    series: dict[int, float] = {}
    for _, group in grouped_counter_rows(table, column).items():
        previous: float | None = None
        for row_index, _row, value in group:
            series[row_index] = 0.0 if previous is None else value - previous
            previous = value
    return series


def summarize_correlations(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    correlations: list[dict[str, Any]] = []
    corr_index = 1
    for table in tables:
        latency_columns = detect_latency_columns(table["columns"])
        candidate_columns = [
            column
            for column in table["columns"]
            if column not in latency_columns and column != "_row_number" and any(to_float(row.get(column)) is not None for row in table["rows"])
        ]
        if not latency_columns or not candidate_columns:
            continue
        pg_columns = set(detect_pg_columns(table["columns"]))
        derived_diffs = {column: diff_series_by_phase(table, column) for column in pg_columns}
        for latency_column in latency_columns:
            latency_by_index = {index: value for index, _row, value in numeric_values(table, latency_column)}
            for column in candidate_columns:
                xs: list[float] = []
                ys: list[float] = []
                for index, row in enumerate(table["rows"]):
                    y = latency_by_index.get(index)
                    if y is None:
                        continue
                    if column in pg_columns:
                        x = derived_diffs[column].get(index)
                    else:
                        x = to_float(row.get(column))
                    if x is None:
                        continue
                    xs.append(float(x))
                    ys.append(float(y))
                if len(xs) < 4 or len(set(xs)) < 2 or len(set(ys)) < 2:
                    continue
                corr = pearson(xs, ys)
                if corr is None:
                    continue
                correlations.append(
                    {
                        "evidence_id": f"corr_{corr_index:03d}",
                        "file": relpath(table["path"]),
                        "metric": f"{column}{' delta' if column in pg_columns else ''}",
                        "latency_metric": latency_column,
                        "method": "pearson",
                        "n": len(xs),
                        "correlation": compact_number(corr, 4),
                    }
                )
                corr_index += 1

    correlations.sort(key=lambda item: abs(item.get("correlation") or 0), reverse=True)
    return correlations[:40]


def summarize_metadata(input_path: Path, input_kind: str, file_truncated: bool, tables: list[dict[str, Any]]) -> dict[str, Any]:
    all_columns = sorted({column for table in tables for column in table["columns"]})
    epoch_values: list[float] = []
    timestamps: list[float] = []
    for table in tables:
        epoch_col = get_column(table["columns"], "Epoch")
        timestamp_col = get_column(table["columns"], "Timestamp", "time", "timestamp")
        if epoch_col:
            epoch_values.extend(value for _, _, value in numeric_values(table, epoch_col))
        if timestamp_col:
            timestamps.extend(value for _, _, value in numeric_values(table, timestamp_col))
    return {
        "path": relpath(input_path),
        "kind": input_kind,
        "files": [
            {
                "path": relpath(table["path"]),
                "format": table["format"],
                "sha256": table["sha256"],
                "rows_read": table["row_count"],
                "columns": table["columns"],
                "truncated": table["truncated"],
            }
            for table in tables
        ],
        "file_scan_truncated": file_truncated,
        "total_rows_read": sum(table["row_count"] for table in tables),
        "column_count": len(all_columns),
        "columns": all_columns[:200],
        "phases": collect_unique(tables, "Phase") or collect_unique(tables, "phase_name"),
        "operations": collect_unique(tables, "Operation") or collect_unique(tables, "operation_name"),
        "request_distributions": collect_unique(tables, "Requestdist"),
        "recordcounts": collect_unique(tables, "Recordcount"),
        "epoch_range": [compact_number(min(epoch_values), 0), compact_number(max(epoch_values), 0)] if epoch_values else None,
        "timestamp_range": [compact_number(min(timestamps), 0), compact_number(max(timestamps), 0)] if timestamps else None,
    }


def build_evidence_summary(input_path: str | Path, max_files: int = 50, max_rows_per_file: int | None = None) -> dict[str, Any]:
    path = Path(input_path).expanduser().resolve()
    existing = load_existing_summary(path) if path.is_file() else None
    if existing is not None:
        return existing

    input_kind, files, file_truncated = input_files(path, max_files)
    tables = [load_table(file_path, max_rows_per_file) for file_path in files]
    if not tables:
        raise RuntimeError(f"No supported input files found under {path}")

    latency = summarize_latency(tables)
    system = summarize_system_patterns(tables)
    pg_stat = summarize_pg_stats(tables)
    correlations = summarize_correlations(tables)

    limitations: list[str] = []
    if not latency["metrics_detected"]:
        limitations.append("No latency-like columns were detected.")
    if not pg_stat["counters_detected"]:
        limitations.append("No PostgreSQL pg_stat-style counters were detected.")
    if any(table["truncated"] for table in tables):
        limitations.append("At least one input file was row-limited during extraction.")
    if file_truncated:
        limitations.append("Directory input contained more files than the extraction limit.")

    return {
        "schema_version": "agent-evidence-v1",
        "created_at_utc": utc_now(),
        "input": summarize_metadata(path, input_kind, file_truncated, tables),
        "latency": latency,
        "system": system,
        "pg_stat": pg_stat,
        "correlations": correlations,
        "limitations": limitations,
        "safety": {
            "mode": "read_only",
            "note": "Evidence extraction reads benchmark data and writes only harness output files.",
        },
    }
