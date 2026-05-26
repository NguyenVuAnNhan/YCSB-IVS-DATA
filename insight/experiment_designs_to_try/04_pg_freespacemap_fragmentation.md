# pg_freespacemap Fragmentation

## Question

Does repeated Zipfian update and vacuum behavior create heap or TOAST free-space fragmentation that helps explain scattered reads, relation growth, or VACC/NOVACC differences?

## Design

Collect compact free-space summaries for:

- `heap`
- `toast_heap`

This is fragmentation evidence, not direct cache evidence.

## Capture Schedule

Default:

```text
after_extend
after_vacuum
before_run
after_run
```

Focus-window additions:

```text
run_progress_5pct
run_progress_10pct
```

## Current Harness Knobs

```bash
SPIKE_TRIGGER_FREESPACE_ENABLED=1
SPIKE_TRIGGER_FREESPACE_SAMPLE_MAX_PAGES=4096
SPIKE_TRIGGER_FREESPACE_BASE_EVENTS="after_extend after_vacuum before_run after_run"
SPIKE_TRIGGER_FREESPACE_FOCUS_EVENTS="run_progress_5pct run_progress_10pct"
```

Set `SPIKE_TRIGGER_FREESPACE_SAMPLE_MAX_PAGES=0` for exact full-relation scanning.

## Output

The harness writes:

```text
${RUN_NAME}_freespace_summary.csv
```

Key columns:

- `relation_pages`
- `sampled_pages`
- `sample_step`
- `estimated_free_bytes`
- `avg_free_bytes`
- `p50_free_bytes`
- `p90_free_bytes`
- `p99_free_bytes`
- `estimated_pages_gt_half_free`

## Analysis

Compare free-space summaries against:

- p95 latency
- run-phase block-read deltas
- page-identity churn
- VACC vs NOVACC late-epoch divergence

