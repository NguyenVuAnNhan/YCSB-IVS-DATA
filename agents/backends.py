from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from . import __version__
from .evidence import utc_now


ROLE_ORDER = ["investigator", "skeptic", "db_internals", "experiment_designer", "summarizer"]


class AgentBackend(Protocol):
    name: str

    def generate(self, role: str, round_index: int, evidence: dict[str, Any], state: dict[str, Any]) -> str:
        ...


def evidence_ref(item: dict[str, Any]) -> str:
    evidence_id = item.get("evidence_id", "evidence")
    file_name = item.get("file", "input")
    metric = item.get("metric") or item.get("latency_metric") or "metric"
    rows = item.get("row_numbers") or item.get("row_number")
    if rows:
        return f"[evidence:{evidence_id} file:{file_name} metric:{metric} rows:{rows}]"
    return f"[evidence:{evidence_id} file:{file_name} metric:{metric}]"


def first_or_none(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return items[0] if items else None


def evidence_pack(evidence: dict[str, Any]) -> dict[str, Any]:
    spikes = evidence.get("latency", {}).get("spike_windows", [])
    correlations = evidence.get("correlations", [])
    jumps = evidence.get("pg_stat", {}).get("notable_counter_jumps", [])
    deltas = evidence.get("pg_stat", {}).get("counter_deltas", [])
    patterns = evidence.get("system", {}).get("patterns", [])
    columns = set(evidence.get("input", {}).get("columns", []))
    files = [entry.get("path", "") for entry in evidence.get("input", {}).get("files", [])]
    text = " ".join(files + list(columns)).lower()
    return {
        "spike": first_or_none(spikes),
        "correlation": first_or_none(correlations),
        "jump": first_or_none(jumps),
        "delta": first_or_none(deltas),
        "pattern": first_or_none(patterns),
        "has_toast_hint": "toast" in text or "json" in text or "arrayjson" in text,
        "has_wal_hint": "wal_bytes" in columns or "walrecords" in text,
        "has_checkpoint_hint": "checkpoints_timed" in columns or "checkpoint" in text,
        "has_buffer_hint": "blks_read" in columns or "blks_hit" in columns or "buffers_alloc" in columns,
        "has_watcher_hint": bool(patterns),
    }


def base_hypotheses(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    pack = evidence_pack(evidence)
    spike = pack["spike"]
    corr = pack["correlation"]
    jump = pack["jump"]
    delta = pack["delta"]
    pattern = pack["pattern"]

    spike_ref = evidence_ref(spike) if spike else "[evidence:none file:input metric:latency]"
    corr_ref = evidence_ref(corr) if corr else "[evidence:none file:input metric:correlation]"
    jump_ref = evidence_ref(jump) if jump else "[evidence:none file:input metric:pg_stat]"
    delta_ref = evidence_ref(delta) if delta else corr_ref
    pattern_ref = evidence_ref(pattern) if pattern else "[evidence:none file:input metric:system]"

    toast_conf = 0.34 + (0.16 if pack["has_toast_hint"] else 0.0) + (0.08 if pack["has_wal_hint"] else 0.0)
    wal_conf = 0.30 + (0.12 if pack["has_wal_hint"] else 0.0) + (0.10 if pack["has_checkpoint_hint"] else 0.0)
    cache_conf = 0.28 + (0.16 if pack["has_buffer_hint"] else 0.0) + (0.06 if corr else 0.0)
    workload_conf = 0.24 + (0.10 if spike and spike.get("phase") else 0.0)
    harness_conf = 0.18 + (0.12 if pack["has_watcher_hint"] else 0.0)

    return [
        {
            "hypothesis_name": "JSONB TOAST rewrite or detoast amplification",
            "mechanism": "Large JSONB values may trigger TOAST fetches, rewrites, index maintenance, and extra WAL around spike windows.",
            "confidence": min(toast_conf, 0.82),
            "supporting_evidence": [
                f"Latency outlier window is present {spike_ref}.",
                f"Write/counter evidence may be relevant to rewrite amplification {delta_ref}.",
            ],
            "counter_evidence": [
                "This harness has not inspected row-level JSONB value sizes or heap/toast table activity directly [role:mock].",
            ],
            "missing_evidence": [
                "Per-window toast table size, pg_stat_io or relation-level IO, and EXPLAIN evidence are missing [role:mock].",
            ],
            "next_test": "With human approval, capture relation-level heap/toast/index bytes and pg_stat_io before, during, and after the spike window.",
            "expected_observation_if_true": "Spike windows should align with increased toast heap/index reads or writes, WAL bytes, and tuple update counters.",
            "expected_observation_if_false": "Spike windows should not align with toast relation activity once phase, operation count, and checkpoint activity are controlled.",
        },
        {
            "hypothesis_name": "Checkpoint, WAL, or fsync pressure",
            "mechanism": "Checkpoint writes, backend writes, WAL volume, or sync time may periodically block foreground YCSB operations.",
            "confidence": min(wal_conf, 0.78),
            "supporting_evidence": [
                f"Potential pg_stat jump or delta is available {jump_ref}.",
                f"Correlation evidence can prioritize WAL/checkpoint counters {corr_ref}.",
            ],
            "counter_evidence": [
                "Cumulative pg_stat counters alone do not prove foreground fsync stalls [role:mock].",
            ],
            "missing_evidence": [
                "Checkpoint log lines, pg_stat_bgwriter deltas by second, and storage latency are missing [role:mock].",
            ],
            "next_test": "With human approval, enable log_checkpoints and collect per-second WAL/checkpoint/storage latency alongside YCSB epochs.",
            "expected_observation_if_true": "Latency spikes should occur at or just after checkpoint sync/write bursts, WAL buffer pressure, or backend write increases.",
            "expected_observation_if_false": "Spikes should persist without nearby checkpoint, WAL, or fsync pressure after synchronized sampling.",
        },
        {
            "hypothesis_name": "Buffer cache or read amplification effect",
            "mechanism": "Changing cache residency or larger records may increase block reads, buffer allocations, or CPU per operation.",
            "confidence": min(cache_conf, 0.74),
            "supporting_evidence": [
                f"System or buffer correlation evidence is available {corr_ref}.",
                f"CPU/RSS/IO pattern evidence is available {pattern_ref}.",
            ],
            "counter_evidence": [
                "Buffer hits and reads can rise with normal workload progress and are not causal by themselves [role:mock].",
            ],
            "missing_evidence": [
                "Shared buffer residency, OS cache state, and relation-level block access are missing [role:mock].",
            ],
            "next_test": "With human approval, compare warm-cache and cold-cache repeats while recording blks_read, blks_hit, buffers_alloc, and relation sizes per epoch.",
            "expected_observation_if_true": "Spikes should strengthen when cache residency worsens or block reads per operation jump.",
            "expected_observation_if_false": "Spikes should remain unchanged across cache-control repeats and not track block-read or allocation deltas.",
        },
        {
            "hypothesis_name": "Workload phase or key-distribution artifact",
            "mechanism": "The spike may be caused by phase transitions, EXTEND/READ mix, zipfian hot keys, or changing record count rather than PostgreSQL internals alone.",
            "confidence": min(workload_conf, 0.62),
            "supporting_evidence": [
                f"Detected spike windows include phase/operation provenance when available {spike_ref}.",
            ],
            "counter_evidence": [
                "A workload artifact does not explain PostgreSQL counter jumps unless the counter movement is phase-coupled [role:mock].",
            ],
            "missing_evidence": [
                "Per-operation mix, key popularity, and client-side retry/error counters around spikes are missing [role:mock].",
            ],
            "next_test": "With human approval, replay a minimal workload with fixed record count, fixed key distribution, and one operation type at a time.",
            "expected_observation_if_true": "Spikes should follow a specific phase, operation, key distribution, or client configuration.",
            "expected_observation_if_false": "Spikes should appear in controlled single-operation repeats with the same PostgreSQL-side signatures.",
        },
        {
            "hypothesis_name": "Measurement harness or watcher artifact",
            "mechanism": "Missing samples, epoch alignment errors, NULL watcher rows, or CSV merge bugs may create apparent correlations or spikes.",
            "confidence": min(harness_conf, 0.52),
            "supporting_evidence": [
                f"Watcher/system pattern evidence can reveal sampling gaps or nulls {pattern_ref}.",
            ],
            "counter_evidence": [
                "YCSB latency percentiles are still benchmark outputs; watcher issues only explain derived correlations unless the YCSB data is also malformed [role:mock].",
            ],
            "missing_evidence": [
                "Raw YCSB logs, watcher timestamps, and merge script audit output are missing [role:mock].",
            ],
            "next_test": "With human approval, rerun only the parsing/merge step on raw logs and compare epoch counts, timestamps, and percentile values byte-for-byte.",
            "expected_observation_if_true": "The apparent spike should move, disappear, or fail to match raw YCSB logs after re-parsing.",
            "expected_observation_if_false": "Raw logs and merged CSVs should agree on spike timing and magnitude.",
        },
    ]


def adapt_hypotheses_for_role(role: str, hypotheses: list[dict[str, Any]], round_index: int) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    for item in hypotheses:
        hypothesis = dict(item)
        confidence = float(hypothesis["confidence"])
        if role == "skeptic":
            hypothesis["confidence"] = max(0.05, round(confidence - 0.08, 3))
            hypothesis["counter_evidence"] = hypothesis["counter_evidence"] + [
                "Alternative explanations remain live until evidence is synchronized at the spike-window level [role:skeptic]."
            ]
        elif role == "db_internals":
            hypothesis["confidence"] = round(confidence, 3)
            hypothesis["supporting_evidence"] = hypothesis["supporting_evidence"] + [
                "Map this against PostgreSQL counters: TOAST relation IO, WAL bytes, checkpoint writes, buffer hits/reads, tuple updates, temp files, and index probes [role:db_internals]."
            ]
        elif role == "experiment_designer":
            hypothesis["confidence"] = round(confidence - 0.02 if round_index == 1 else confidence, 3)
            hypothesis["next_test"] = "Human approval required before changing experiments. " + hypothesis["next_test"]
        elif role == "summarizer":
            hypothesis["confidence"] = round(confidence, 3)
        else:
            hypothesis["confidence"] = round(confidence + (0.01 * (round_index - 1)), 3)
        adjusted.append(hypothesis)
    adjusted.sort(key=lambda entry: entry["confidence"], reverse=True)
    return adjusted


def taxonomy() -> list[dict[str, str]]:
    return [
        {"name": "storage_sync", "description": "Checkpoint, WAL, fsync, or backend-write pressure."},
        {"name": "toast_amplification", "description": "JSONB/TOAST fetch, rewrite, compression, or index maintenance amplification."},
        {"name": "cache_residency", "description": "Buffer cache, OS cache, block-read, or memory-residency changes."},
        {"name": "workload_shape", "description": "Phase, operation mix, key distribution, or record-count artifact."},
        {"name": "measurement_integrity", "description": "Watcher gaps, merge bugs, timestamp skew, or client-side reporting issues."},
    ]


class MockBackend:
    name = "mock"

    def generate(self, role: str, round_index: int, evidence: dict[str, Any], state: dict[str, Any]) -> str:
        hypotheses = adapt_hypotheses_for_role(role, base_hypotheses(evidence), round_index)
        payload = {
            "schema_version": "agent-output-v1",
            "backend": self.name,
            "harness_version": __version__,
            "created_at_utc": utc_now(),
            "role": role,
            "round": round_index,
            "hypotheses": hypotheses,
            "notes": [
                f"Deterministic mock output for {role}; replace backend for model-generated critique.",
                "Agents are not allowed to run shell commands or mutate benchmark data.",
            ],
            "recommended_tests": sorted({hypothesis["next_test"] for hypothesis in hypotheses})[:8],
            "taxonomy": taxonomy() if role == "summarizer" else [],
        }
        return json.dumps(payload, indent=2, sort_keys=True)


class OpenAICompatibleChatBackend:
    """Small OpenAI-compatible /v1/chat/completions backend using stdlib HTTP."""

    name = "openai-compatible"

    def __init__(self) -> None:
        self.base_url = os.environ.get("AGENT_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("AGENT_LLM_MODEL", "")
        self.api_key = os.environ.get("AGENT_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        if not self.model:
            raise RuntimeError("AGENT_LLM_MODEL must be set for the openai-compatible backend.")
        if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise RuntimeError("AGENT_LLM_API_KEY or OPENAI_API_KEY must be set for non-local LLM endpoints.")

    def generate(self, role: str, round_index: int, evidence: dict[str, Any], state: dict[str, Any]) -> str:
        prompt = build_prompt(role, round_index, evidence, state)
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a read-only PostgreSQL/YCSB benchmark analysis agent. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM backend request failed: {exc}") from exc
        return payload["choices"][0]["message"]["content"]


def build_prompt(role: str, round_index: int, evidence: dict[str, Any], state: dict[str, Any]) -> str:
    compact_state = {
        "previous_outputs": [
            {
                "role": output.get("role"),
                "round": output.get("round"),
                "valid": output.get("valid"),
                "hypotheses": (output.get("payload") or {}).get("hypotheses", [])[:5],
                "errors": output.get("errors", []),
            }
            for output in state.get("agent_outputs", [])[-10:]
        ]
    }
    return json.dumps(
        {
            "task": "Produce adversarial PostgreSQL/YCSB latency-spike hypotheses. Do not suggest mutating data or running commands.",
            "role": role,
            "round": round_index,
            "required_hypothesis_fields": [
                "hypothesis_name",
                "mechanism",
                "confidence",
                "supporting_evidence",
                "counter_evidence",
                "missing_evidence",
                "next_test",
                "expected_observation_if_true",
                "expected_observation_if_false",
            ],
            "output_contract": {
                "schema_version": "agent-output-v1",
                "role": role,
                "round": round_index,
                "hypotheses": "list of hypothesis objects using the required fields",
                "notes": "list of short strings",
                "recommended_tests": "list of tests; each must say human approval is required before experiment changes",
                "taxonomy": "summarizer only: reusable anomaly taxonomy",
            },
            "provenance_rule": "Every evidence claim must cite an evidence_id, file, metric, or agent role.",
            "evidence_summary": evidence,
            "conversation_state": compact_state,
        },
        indent=2,
        sort_keys=True,
    )


def build_backend(name: str | None = None) -> AgentBackend:
    backend_name = (name or os.environ.get("AGENT_LLM_BACKEND") or "mock").strip().lower()
    if backend_name in {"mock", "deterministic", ""}:
        return MockBackend()
    if backend_name in {"openai-compatible", "openai", "ollama"}:
        return OpenAICompatibleChatBackend()
    raise ValueError(f"Unsupported backend '{backend_name}'. Supported: mock, openai-compatible.")
