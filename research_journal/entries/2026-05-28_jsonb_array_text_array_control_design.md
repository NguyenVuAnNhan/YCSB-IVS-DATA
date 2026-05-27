# JSONB Array, Native Array, And TEXT Control Experiment

- Date: 2026-05-28
- Workspace: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`
- Related repo: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`
- Status: draft

## Context

The current FULL_VIEW and NOVACC evidence suggests that PostgreSQL pain comes from a combination of:

- large TOAST-backed values,
- repeated value rewrites during append-style growth,
- WAL and physical storage amplification,
- useful TOAST page residency exceeding cache,
- detoast, serialization, and client parse costs during reads.

The open question is whether this is specific to `JSONB` arrays or whether native PostgreSQL large values such as `TEXT` and `TEXT[]` show the same behavior with different magnitude.

Existing scripts already cover the conceptual variants:

- `experiment_postgresql_baseline.sh`: `TEXT` columns.
- `experiment_postgresql_array_baseline.sh`: `TEXT[]` columns.
- `experiment_postgresql_array_json.sh`: `JSONB` columns containing JSON arrays.

The new experiment should bring these under the same observability harness and control logical byte growth across all three variants.

## Notes

### Research Questions

1. Does `JSONB ARRAY` produce more physical storage, WAL, TOAST block work, and read latency than `TEXT[]` or `TEXT` for the same logical bytes appended?
2. Are the late read spikes primarily a generic large-varlena/TOAST rewrite effect, or does `JSONB` add a distinct structural and serialization penalty?
3. Does reducing `shared_buffers` shift the phase change earlier for all variants, or mainly for `JSONB ARRAY`?
4. Can we separate server-side detoast/materialization from client-side parsing/decoding?

### Hypotheses

H1. All three variants will show rewrite amplification once values become large, because `TEXT`, `TEXT[]`, and `JSONB` are all varlena values that can be TOASTed.

H2. `JSONB ARRAY` will have the steepest tail-latency curve because generic TOAST rewrite amplification is combined with JSONB structural overhead and JSON serialization/parsing.

H3. `TEXT[]` will sit between `TEXT` and `JSONB ARRAY`: it is still a structured varlena container and still rewritten on append, but should avoid JSONB's binary JSON container and JSON parse cost.

H4. `TEXT` will have the lowest CPU and structural overhead, but can still show large TOAST/WAL/cache amplification when values grow enough.

H5. Smaller `shared_buffers` will move the read-tail phase change earlier. The shift should be strongest where physical TOAST working set and read materialization cost are largest.

### Critical Control: Payload Compressibility

Do not use repeated characters such as `"aaaa..."` as the appended payload. PostgreSQL TOAST compression can make `TEXT` look artificially good and can also change JSONB/array physical size in uneven ways.

Use deterministic low-compressibility payload chunks:

- fixed seed,
- alphanumeric or byte-safe strings,
- same logical byte length per append across variants,
- same key/update schedule across variants,
- record the payload generator seed in `manifest.json`.

An optional follow-up can intentionally compare compressible versus low-compressibility payloads, but the primary control experiment should use low-compressibility data.

## Design

### Variants

Run the same workload shape for:

| Variant | PostgreSQL schema | Append semantics | Logical size SQL |
|---|---|---|---|
| `text_scalar` | `field0 TEXT ... field9 TEXT` | concatenate one fixed-size chunk onto one field | `octet_length(field0) + ... + octet_length(field9)` |
| `text_array` | `field0 TEXT[] ... field9 TEXT[]` | `array_append` or equivalent with one fixed-size text element | `sum(octet_length(elem))` across `unnest(fieldN)` |
| `jsonb_array` | `field0 JSONB ... field9 JSONB` | append one fixed-size JSON string element to the JSONB array | existing `jsonb_array_elements_text` size query |

Optional later variant:

| Variant | Rationale |
|---|---|
| `jsonb_scalar_string` | Separates JSONB scalar storage from JSONB array container overhead. Lower priority than the three primary variants. |

### Primary Run Matrix

Start with a same-host, same-configuration heavy NOVACC matrix to avoid vacuum as a first-order confound:

| Dimension | Setting |
|---|---|
| Scale | `heavy` |
| Records | `10,000` |
| Extend operations per phase | `100,000` |
| Run operations per phase | `100,000` |
| Epochs | `10 x 10` |
| Extend distribution | `zipfian` |
| Read distribution | `uniform` |
| Workload after extend | pure read |
| Vacuum | off for primary matrix |
| `shared_buffers` | `4GB` |
| Replicates | at least 2 if disk/time allows |
| Variants | `text_scalar`, `text_array`, `jsonb_array` |

Recommended run ids:

```text
type_control_text_heavy_novacc_run1
type_control_text_array_heavy_novacc_run1
type_control_jsonb_array_heavy_novacc_run1
```

Run order should be randomized or rotated across replicates to reduce host drift. Each run should reset the database, confirm extensions after reset, and capture the same PostgreSQL settings.

### Secondary Cache Sweep

After the primary matrix, run a cache-size sweep on the same host:

| shared_buffers | Priority |
|---:|---|
| `4GB` | baseline |
| `1GB` | medium |
| `512MB` | high |
| `128MB` | high |

Use `light` first to control cost, then `heavy` for the most informative variants. The expected result is not simply "small cache makes everything bad"; the specific prediction is that the phase change moves left as the useful TOAST working set exceeds cache earlier.

Suggested staged sweep:

1. `light`, all three variants, `4GB` and `128MB`.
2. `heavy`, `jsonb_array` and `text_array`, `4GB`, `512MB`, and `128MB`.
3. Add `text_scalar` heavy cache sweep if the first two stages leave ambiguity.

### Vacuum Follow-Up

After NOVACC establishes the type effect, rerun the primary heavy matrix with `VACUUM_ENABLED=1`.

Purpose:

- determine whether vacuum amplifies all large-varlena variants or mainly JSONB,
- compare free-space and page-residency changes,
- test whether JSONB-specific serialization remains visible after vacuum equalizes dead tuple state.

## Required Harness Work

The evidence-producing version should use the current full observability harness. Minimal implementation target:

1. Add a storage-kind switch such as:

```text
VALUE_STORAGE_KIND=text_scalar | text_array | jsonb_array
```

2. Generalize table creation by storage kind.

3. Generalize extend operation in the PostgreSQL binding or harness path while preserving the same YCSB workload semantics.

4. Generalize logical size collection:

- `TEXT`: direct `octet_length`.
- `TEXT[]`: `unnest` and sum element byte length.
- `JSONB ARRAY`: existing `jsonb_array_elements_text` sum.

5. Generalize detoast/materialization probes:

- lookup-only primary-key probe,
- full-value materialization probe,
- serialized output-size probe,
- server-side execution time,
- client decode/parse time where relevant.

6. Keep `pg_stat_statements`, `pg_stat_io`, `pg_statio_user_tables`, relation sizes, WAL range summaries, freespace summaries, and targeted `pg_buffercache` page identity capture.

7. Keep page identity targeted to avoid enormous result pulls:

- always capture `before_run`, `1%`, `5%`, `10%`, and `after_run`,
- capture all epochs at relation-level,
- capture page identity for selected epochs such as `1, 10, 25, 50, 75, 90, 100`,
- optionally add more page-identity epochs only after seeing spike windows.

## Metrics To Compare

Primary normalized metrics:

- P50/P95/P99/max read latency by epoch and variant.
- WAL bytes/op and WAL bytes/logical byte.
- Total relation bytes/logical byte.
- TOAST heap bytes/logical byte.
- TOAST index bytes/logical byte.
- TOAST blocks/op and TOAST index blocks/op.
- `pg_stat_io` reads, evictions, writes, fsyncs by backend/object/context.
- Cache-hit ratio from `pg_statio_user_tables`.
- Page-identity overlap from `before_run` to early run snapshots.
- HOT update ratio, new-page update ratio, dead tuples/update.
- Checkpoint/bgwriter/writeback counters.
- Server execution share versus client parse/decode share.

Key derived outputs:

- `type_variant_phase_deltas.csv`
- `type_variant_normalized_metrics.csv`
- `type_variant_storage_amplification.csv`
- `type_variant_cache_residency.csv`
- `type_variant_latency_by_value_size.csv`
- `type_variant_summary.md`

## Expected Outcomes

Expected ranking if the current model is right:

```text
storage/WAL/read-tail severity:
JSONB ARRAY >= TEXT[] >= TEXT

server CPU / serialization / client parse severity:
JSONB ARRAY > TEXT[] >= TEXT

cache-size sensitivity:
largest for JSONB ARRAY, visible for TEXT[], weakest for TEXT
```

If `TEXT` and `TEXT[]` show nearly the same physical amplification and read tails as `JSONB ARRAY`, then the mechanism is mostly generic large-varlena TOAST rewrite behavior.

If `JSONB ARRAY` is much worse after normalizing by logical bytes and TOAST blocks/op, then JSONB structural materialization and JSON serialization/parsing are major additional mechanisms.

If smaller cache moves phase changes left for all variants, that supports useful-page residency as a generic trigger. If it only moves JSONB, then the JSONB physical/CPU shape is probably creating a unique working-set problem.

## Decisions

Prioritize this experiment after one clean heavy VACC/NOVACC comparison and before adding more speculative modules. It directly tests whether our current explanation is PostgreSQL-large-value general or JSONB-array specific.

Do not over-expand the matrix initially. The first evidence-producing run should be:

```text
heavy NOVACC, 4GB shared_buffers, zipfian extend, uniform pure read
variants: TEXT, TEXT[], JSONB ARRAY
```

Then run cache sweep only after confirming the type effect.

## Next Actions

1. Implement `VALUE_STORAGE_KIND` support in the full observability harness.
2. Smoke test all three variants locally with tiny counts.
3. Run one light EC2 smoke test with full visibility and targeted page identity.
4. Run the primary heavy NOVACC matrix on the same EC2 instance.
5. Compare type variants with normalized physical/logical metrics before launching the cache sweep.
