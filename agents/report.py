from __future__ import annotations

from collections import defaultdict
from typing import Any


def valid_payloads(state: dict[str, Any], role: str | None = None) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for output in state.get("agent_outputs", []):
        if not output.get("valid"):
            continue
        payload = output.get("payload") or {}
        if role is None or payload.get("role") == role:
            payloads.append(payload)
    return payloads


def final_hypotheses(state: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    summarizers = valid_payloads(state, "summarizer")
    if summarizers:
        payload = summarizers[-1]
        return "summarizer", sorted(payload.get("hypotheses", []), key=lambda item: item.get("confidence", 0), reverse=True)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for payload in valid_payloads(state):
        for hypothesis in payload.get("hypotheses", []):
            grouped[hypothesis["hypothesis_name"]].append(hypothesis)

    combined: list[dict[str, Any]] = []
    for name, items in grouped.items():
        first = dict(items[0])
        first["confidence"] = round(sum(float(item["confidence"]) for item in items) / len(items), 3)
        for field in ["supporting_evidence", "counter_evidence", "missing_evidence"]:
            merged: list[str] = []
            for item in items:
                for value in item.get(field, []):
                    if value not in merged:
                        merged.append(value)
            first[field] = merged[:8]
        combined.append(first)
    return "aggregate", sorted(combined, key=lambda item: item.get("confidence", 0), reverse=True)


def one_line(values: list[str], fallback: str = "n/a") -> str:
    if not values:
        return fallback
    return "<br>".join(str(value) for value in values[:3])


def evidence_rows(evidence: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in evidence.get("latency", {}).get("spike_windows", [])[:12]:
        rows.append(
            {
                "id": item.get("evidence_id", ""),
                "type": "latency_spike",
                "file": item.get("file", ""),
                "metric": item.get("metric", ""),
                "where": f"phase={item.get('phase')} op={item.get('operation')} epoch={item.get('epoch_start')}-{item.get('epoch_end')}",
                "finding": f"peak={item.get('peak_value')} baseline_median={item.get('baseline_median')} severity={item.get('severity_ratio')}",
            }
        )
    for item in evidence.get("correlations", [])[:12]:
        rows.append(
            {
                "id": item.get("evidence_id", ""),
                "type": "correlation",
                "file": item.get("file", ""),
                "metric": item.get("metric", ""),
                "where": f"against={item.get('latency_metric')} n={item.get('n')}",
                "finding": f"{item.get('method')}={item.get('correlation')}",
            }
        )
    for item in evidence.get("pg_stat", {}).get("notable_counter_jumps", [])[:12]:
        rows.append(
            {
                "id": item.get("evidence_id", ""),
                "type": "pg_counter_jump",
                "file": item.get("file", ""),
                "metric": item.get("metric", ""),
                "where": f"phase={item.get('phase')} epoch={item.get('epoch')} row={item.get('row_number')}",
                "finding": f"delta={item.get('delta')} threshold={item.get('threshold')}",
            }
        )
    for item in evidence.get("system", {}).get("patterns", [])[:8]:
        rows.append(
            {
                "id": item.get("evidence_id", ""),
                "type": "system_pattern",
                "file": item.get("file", ""),
                "metric": item.get("metric", ""),
                "where": f"peak_epoch={item.get('peak_epoch_start')}-{item.get('peak_epoch_end')}",
                "finding": f"min={item.get('min')} mean={item.get('mean')} max={item.get('max')}",
            }
        )
    return rows


def render_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("\n", " ") for value in row) + " |")
    return "\n".join(lines) + "\n"


def render_report(evidence: dict[str, Any], state: dict[str, Any]) -> str:
    source_role, hypotheses = final_hypotheses(state)
    top = hypotheses[:5]
    input_info = evidence.get("input", {})
    invalid_outputs = [output for output in state.get("agent_outputs", []) if not output.get("valid")]
    report_lines: list[str] = []

    report_lines.append("# Agent Investigation Report")
    report_lines.append("")
    report_lines.append("## Executive Summary")
    report_lines.append("")
    report_lines.append(
        "Agents suggest hypotheses, not conclusions. Human approval is required before applying any experimental change. "
        f"[role:summarizer source:{source_role}]"
    )
    report_lines.append(
        f"Input `{input_info.get('path')}` produced {len(evidence.get('latency', {}).get('spike_windows', []))} latency spike windows, "
        f"{len(evidence.get('correlations', []))} suspicious correlations, and "
        f"{len(evidence.get('pg_stat', {}).get('notable_counter_jumps', []))} notable PostgreSQL counter jumps. "
        "[file:input metric:evidence_summary]"
    )
    if top:
        report_lines.append(
            "Highest-ranked mock/adversarial explanation: "
            f"**{top[0]['hypothesis_name']}** at confidence {top[0]['confidence']}. [role:{source_role}]"
        )
    if evidence.get("limitations"):
        report_lines.append("Limitations: " + "; ".join(evidence["limitations"]) + " [file:input metric:limitations]")

    report_lines.append("")
    report_lines.append("## Ranked Hypotheses")
    report_lines.append("")
    report_lines.append(
        render_table(
            ["Rank", "Hypothesis", "Confidence", "Mechanism", "Support", "Next Test"],
            [
                [
                    index,
                    item["hypothesis_name"],
                    item["confidence"],
                    item["mechanism"] + f" [role:{source_role}]",
                    one_line(item.get("supporting_evidence", [])),
                    item["next_test"] + f" [role:{source_role}]",
                ]
                for index, item in enumerate(top, start=1)
            ],
        )
    )

    report_lines.append("## Evidence Table")
    report_lines.append("")
    rows = evidence_rows(evidence)
    report_lines.append(
        render_table(
            ["Evidence ID", "Type", "File", "Metric", "Where", "Finding"],
            [[row["id"], row["type"], row["file"], row["metric"], row["where"], row["finding"]] for row in rows],
        )
    )

    report_lines.append("## Counter-Evidence")
    report_lines.append("")
    counter_rows = []
    for item in top:
        counter_rows.append(
            [
                item["hypothesis_name"],
                one_line(item.get("counter_evidence", [])),
                one_line(item.get("missing_evidence", [])),
                f"[role:{source_role}]",
            ]
        )
    report_lines.append(render_table(["Hypothesis", "Counter-Evidence", "Missing Evidence", "Provenance"], counter_rows))

    report_lines.append("## Recommended Next Experiments")
    report_lines.append("")
    experiments = valid_payloads(state, "experiment_designer")
    recommended: list[str] = []
    for payload in experiments:
        for test in payload.get("recommended_tests", []):
            if test not in recommended:
                recommended.append(test)
    if not recommended:
        recommended = [item["next_test"] for item in top]
    for index, test in enumerate(recommended[:8], start=1):
        report_lines.append(f"{index}. {test} [role:experiment_designer]")

    report_lines.append("")
    report_lines.append("## Reusable Anomaly Taxonomy")
    report_lines.append("")
    taxonomy_items = []
    summarizers = valid_payloads(state, "summarizer")
    if summarizers:
        taxonomy_items = summarizers[-1].get("taxonomy", [])
    if taxonomy_items:
        for item in taxonomy_items:
            if isinstance(item, dict):
                report_lines.append(f"- `{item.get('name')}`: {item.get('description')} [role:summarizer]")
            else:
                report_lines.append(f"- {item} [role:summarizer]")
    else:
        report_lines.append("- No taxonomy was produced by a valid summarizer output. [role:summarizer]")

    report_lines.append("")
    report_lines.append("## Audit Notes")
    report_lines.append("")
    report_lines.append(f"- Backend: `{state.get('backend')}` [role:harness]")
    report_lines.append(f"- Rounds requested: `{state.get('rounds_requested')}` [role:harness]")
    report_lines.append(f"- Agent outputs: `{len(state.get('agent_outputs', []))}` [role:harness]")
    report_lines.append(f"- Invalid outputs preserved: `{len(invalid_outputs)}` [role:harness]")
    report_lines.append("- Full structured state is in `state.json`; raw per-agent records are in `agent_logs.jsonl`. [role:harness]")

    return "\n".join(report_lines).rstrip() + "\n"
