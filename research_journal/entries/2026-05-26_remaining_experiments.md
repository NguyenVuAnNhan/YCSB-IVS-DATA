# Remaining Experiment Plan

- Date: 2026-05-26
- Workspace: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`
- Related repo: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`
- Status: active

## Context

The current harness has expanded observability for PostgreSQL/YCSB value-size experiments, including phase snapshots, continuous sampling, normalized metrics, pg_buffercache-related visibility, pg_freespacemap ideas, pg_stat_statements, pg_walinspect support, and pg_prewarm intervention support. We have also added two practical scale modes so runs no longer require hand-setting every count variable.

The mechanism is better constrained but not fully closed. Existing FULL_VIEW runs suggest cache residency and/or run-environment differences matter, and one EC2 host had disk-space/history confounds. The remaining work should prioritize clean, comparable runs over adding more instrumentation.

## Scale Modes

- `light`: paper-matching lightweight scale for checking whether the mechanism appears under smaller data volume.
- `heavy`: larger operational scale for stressing TOAST, cache, WAL, checkpoints, and storage growth more clearly.

Use the script-level scale flag instead of manually setting count variables when possible:

```bash
./run_postgresql_array_json_full_visibility.sh --scale light
./run_postgresql_array_json_full_visibility.sh --scale heavy
```

## Required Environment

Before launching long runs, confirm:

- PostgreSQL 16 or newer is preferred for `pg_stat_io`.
- `track_io_timing=on`.
- `log_checkpoints=on`.
- `pg_stat_statements` is in `shared_preload_libraries`.
- Optional extensions are installed or at least available where relevant: `pg_buffercache`, `pg_freespacemap`, `pg_stat_statements`, `pg_walinspect`, `pg_prewarm`.
- The benchmark user has permissions to create/use the needed extensions after database reset.
- Disk headroom is sufficient for a full run.
- The run uses tmux and the full-visibility launcher so stdout/stderr can be inspected live.

## Core Matrix

1. Heavy VACC baseline
   - Scale: `heavy`
   - Vacuum: on
   - Priority: highest
   - Rationale: this is the main stressed baseline. It has been run, but one host had disk/history confounds, so a clean rerun is useful.

2. Heavy NOVACC baseline
   - Scale: `heavy`
   - Vacuum: off
   - Priority: highest
   - Status: running as `full_view_heavy_novacc_run1` on EC2 host `13.236.86.169`, started 2026-05-26T09:26:23Z.
   - Rationale: counterpart to heavy VACC; tests whether vacuum/free-space churn materially changes latency, WAL, dead tuples, and TOAST-related behavior.

3. Light VACC baseline
   - Scale: `light`
   - Vacuum: on
   - Priority: medium
   - Rationale: paper-matching lightweight scale; checks whether the same mechanism appears without heavy-scale pressure.

4. Light NOVACC baseline
   - Scale: `light`
   - Vacuum: off
   - Priority: medium
   - Rationale: completes the scale by vacuum matrix and gives a cleaner comparison against the heavy NOVACC run.

## Intervention Runs

5. Heavy pg_prewarm, TOAST index only
   - Scale: `heavy`
   - Vacuum: match the baseline being compared
   - Intervention: `SPIKE_TRIGGER_PREWARM_ENABLED=1`, `SPIKE_TRIGGER_PREWARM_MODE=toast_index`
   - Priority: high after the clean heavy baselines
   - Rationale: if p95/p99 improves after warming the TOAST index, that is evidence consistent with cache-residency sensitivity.

6. Heavy pg_prewarm, heap plus TOAST index
   - Scale: `heavy`
   - Vacuum: match the prior intervention
   - Intervention: `SPIKE_TRIGGER_PREWARM_MODE=heap_toast_index`
   - Priority: conditional
   - Rationale: only needed if TOAST-index-only warming helps or is ambiguous. It tests whether broader relation warming changes the result.

## Optional Follow-Ups

7. Focused auto_explain rerun
   - Use only around late peak windows, not as a default full-run setting.
   - Rationale: useful if we still need server-side plan/buffer proof for a specific spike pattern.

8. Large Object control
   - Priority: low
   - Rationale: possible control if TOAST page identity remains ambiguous and we need a cleaner key-to-page mapping story.

## Recommended Order

1. Heavy VACC clean rerun.
2. Heavy NOVACC.
3. Light VACC.
4. Light NOVACC.
5. Heavy pg_prewarm with `toast_index`.
6. Heavy pg_prewarm with `heap_toast_index`, if the first intervention is promising or ambiguous.

## What Success Looks Like

The next analysis should be able to compare normalized costs across scale and vacuum modes:

- WAL bytes per operation and per logical byte.
- Storage growth per operation and per logical byte.
- TOAST heap/index blocks per operation.
- Cache hit ratio versus p95/p99 latency.
- HOT update ratio and dead tuples per update.
- Checkpoint/bgwriter/WAL timing signals where available.
- Whether pg_prewarm materially changes tail latency.

The goal is not a prettier log set. The goal is evidence about which PostgreSQL subsystems become expensive as logical value size grows.
