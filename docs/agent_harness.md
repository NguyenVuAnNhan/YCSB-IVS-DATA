# Local Agent Harness

This harness produces read-only, adversarial hypothesis reports for PostgreSQL/YCSB latency spikes. It is intentionally small: Python modules under `agents/`, JSON state files, JSONL audit logs, and a Markdown report.

Agents suggest hypotheses, not conclusions. Human approval is required before changing an experiment, rerunning a benchmark, or applying any diagnostic change.

## CLI Usage

```bash
python -m agents.run \
  --input DATA/postgresql_run1_uniform_heavy.csv \
  --out runs/agent_investigation_001 \
  --rounds 2
```

Use `python3` in place of `python` on systems without a `python` alias.

Smoke test:

```bash
python -m agents.run --input tests/fixtures/sample_metrics.csv --out /tmp/agent_test --rounds 1
python -m unittest tests.test_agent_harness_smoke
```

## Inputs

`--input` accepts:

- CSV files with headers, such as the YCSB benchmark CSVs in `DATA/` or `JSON_BLUE/`.
- `.metrics` watcher files with rows shaped as `Phase,Epoch,Timestamp,CPU,MemoryKB,DeltaReadBytes,DeltaWriteBytes`.
- JSON or JSONL files containing either a list of row objects or an existing `evidence_summary.json`.
- Parquet files only if pandas and a parquet engine are already installed in the environment.
- A directory, in which case supported files are scanned read-only up to `--max-files`.

No benchmark input is mutated. The harness writes only to `--out`.

## Outputs

The output directory contains:

- `evidence_summary.json`: compact extracted evidence, including input provenance, latency spike windows, CPU/RSS or IO patterns, PostgreSQL counter deltas/jumps, and suspicious correlations.
- `state.json`: full harness state and validated agent outputs.
- `agent_logs.jsonl`: append-only audit log with raw agent output and validation status.
- `report.md`: executive summary, ranked hypotheses, evidence table, counter-evidence, next experiments, and anomaly taxonomy.

Every report claim should cite an input file/metric/evidence id or an agent role.

## Agent Roles

- `investigator`: proposes candidate explanations for latency spikes.
- `skeptic`: challenges each hypothesis and names missing evidence.
- `db_internals`: maps evidence to PostgreSQL internals such as TOAST, WAL, checkpoints, buffers, temp files, tuple counters, and index behavior.
- `experiment_designer`: proposes minimal diagnostics; experiment changes require human approval.
- `summarizer`: ranks hypotheses and emits a reusable anomaly taxonomy.

Each hypothesis uses the same JSON fields: `hypothesis_name`, `mechanism`, `confidence`, `supporting_evidence`, `counter_evidence`, `missing_evidence`, `next_test`, `expected_observation_if_true`, and `expected_observation_if_false`.

## LLM Backends

The default backend is deterministic and needs no API key:

```bash
python -m agents.run --input tests/fixtures/sample_metrics.csv --out /tmp/agent_test --rounds 1
```

To use an OpenAI-compatible chat-completions endpoint later, set environment variables:

```bash
export AGENT_LLM_BACKEND=openai-compatible
export AGENT_LLM_MODEL=<model-name>
export AGENT_LLM_BASE_URL=https://api.openai.com/v1
export OPENAI_API_KEY=<key-from-env-only>
python -m agents.run --input DATA/postgresql_run1_uniform_heavy.csv --out runs/agent_real_backend_001 --rounds 2
```

For local OpenAI-compatible servers such as Ollama, point `AGENT_LLM_BASE_URL` at the local `/v1` endpoint and set `AGENT_LLM_MODEL`. The code does not hardcode secrets.

## Limitations

- The extractor uses simple robust thresholds and Pearson correlations. It is meant to triage, not prove causality.
- Cumulative PostgreSQL counters are differenced by phase when possible, but synchronized per-second telemetry is stronger evidence.
- JSONB/TOAST hypotheses remain speculative unless relation-level heap/toast/index IO or size evidence is collected.
- Mock agents are schema-valid placeholders. They are useful for reproducible plumbing tests, not for final scientific claims.
