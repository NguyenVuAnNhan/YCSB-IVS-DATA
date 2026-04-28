# JSONB TOAST Amplification Experiment Plan

## Goal

Confirm whether the late main-run p95 latency spikes in JSON Blue are caused by PostgreSQL JSONB/TOAST amplification, and identify the internal mechanism clearly enough to distinguish:

-   logical value-size growth
-   physical TOAST rewrite/chunk amplification
-   heap/TOAST bloat and locality loss
-   vacuum/checkpoint perturbation
-   server-side detoast and JSONB serialization
-   client-side JSON parsing/conversion cost

Data lives in:

-   `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`

Experiment harness lives in:

-   `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`

## Core Hypothesis

Append-heavy JSONB arrays are not append logs. Each `EXTEND` rewrites a JSONB datum:

``` sql
field = COALESCE(field, '[]'::jsonb) || jsonb_build_array(CAST(? AS text))
```

As Zipfian hot rows grow, PostgreSQL repeatedly creates new heap tuple versions and new TOAST chunks. Late read phases then hit large toasted values often enough that detoast, TOAST chunk fetch, JSONB-to-text serialization, and JDBC parsing enter the 95th percentile.

## Experiment Stages

### Stage 1: Add PostgreSQL Storage Instrumentation

Add a per-phase probe to the PostgreSQL ArrayJSON harness. Collect it after:

-   initial load
-   every `extend`
-   every `VACUUM (ANALYZE)`
-   every main `run`
-   every `reference`
-   every `clean-run`
-   every `avg-run`

Recommended output file:

``` text
analysis/Data/Internal_data/postgresql_arrayjson_toast_storage_<run_name>.csv
```

Capture at least:

-   iteration
-   phase
-   timestamp
-   heap table name
-   heap bytes
-   heap total bytes
-   toast relid
-   toast heap bytes
-   toast total bytes
-   toast index bytes
-   total relation bytes
-   `pg_stat_user_tables.n_live_tup`
-   `pg_stat_user_tables.n_dead_tup`
-   `pg_stat_user_tables.n_tup_ins`
-   `pg_stat_user_tables.n_tup_upd`
-   `pg_stat_user_tables.n_tup_hot_upd`
-   `pg_stat_user_tables.vacuum_count`
-   `pg_stat_user_tables.autovacuum_count`
-   database-level `blks_read`, `blks_hit`, `temp_files`, `temp_bytes`
-   WAL counters from `pg_stat_wal`
-   checkpoint/background writer counters from `pg_stat_bgwriter`

Probe query:

``` sql
WITH heap AS (
  SELECT
    c.oid AS heap_oid,
    c.relname AS heap_name,
    c.reltoastrelid AS toast_oid
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relname = 'usertable'
),
toast AS (
  SELECT
    h.heap_oid,
    h.heap_name,
    h.toast_oid,
    t.relname AS toast_name,
    ti.indexrelid AS toast_index_oid
  FROM heap h
  LEFT JOIN pg_class t ON t.oid = h.toast_oid
  LEFT JOIN pg_index ti ON ti.indrelid = h.toast_oid
)
SELECT
  heap_name,
  toast_name,
  pg_relation_size(heap_oid) AS heap_bytes,
  pg_total_relation_size(heap_oid) AS heap_total_bytes,
  CASE WHEN toast_oid = 0 THEN 0 ELSE pg_relation_size(toast_oid) END AS toast_heap_bytes,
  CASE WHEN toast_oid = 0 THEN 0 ELSE pg_total_relation_size(toast_oid) END AS toast_total_bytes,
  CASE WHEN toast_index_oid IS NULL THEN 0 ELSE pg_relation_size(toast_index_oid) END AS toast_index_bytes
FROM toast;
```

Expected confirmation:

-   TOAST size grows superlinearly with late p95.
-   `tup_inserted/op` rises while logical `tup_updated/op` stays near 1.
-   `n_dead_tup`, vacuum duration, WAL bytes, and buffer allocations rise with TOAST growth.

Falsifier:

-   Main-run p95 spikes without meaningful TOAST growth, bloat growth, detoast cost, or WAL/buffer amplification.

### Stage 2: Add Deterministic Detoast Probes

The existing plan probe uses:

``` sql
SELECT * FROM usertable WHERE ycsb_key = '<key>';
```

That confirms primary-key lookup cost, but it may not expose full detoast and serialization cost. Replace or supplement it with probes that force JSONB materialization.

For selected keys:

``` sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
  octet_length(field0::text) +
  octet_length(field1::text) +
  octet_length(field2::text) +
  octet_length(field3::text) +
  octet_length(field4::text) +
  octet_length(field5::text) +
  octet_length(field6::text) +
  octet_length(field7::text) +
  octet_length(field8::text) +
  octet_length(field9::text) AS logical_json_text_bytes
FROM usertable
WHERE ycsb_key = '<key>';
```

Select keys from the current value-size distribution:

-   minimum-size key
-   median key
-   p90 key
-   p95 key
-   p99 key
-   max key

Recommended output:

``` text
analysis/Data/Internal_data/postgresql_arrayjson_detoast_probe_<run_name>.log
```

Expected confirmation:

-   Lookup-only plans remain cheap.
-   Detoast-forcing plans grow sharply with key size.
-   p95/p99/max keys show more shared reads/hits and much higher execution time.

Falsifier:

-   Detoast-forcing execution time remains flat across small and large keys.

### Stage 3: Separate Server Detoast From Client JSON Parsing

Run three read variants over the same post-extend table state.

Variant A: key-only read

``` sql
SELECT ycsb_key FROM usertable WHERE ycsb_key = ?;
```

Variant B: server detoast and serialize, no Java JSON parsing

``` sql
SELECT field0::text, field1::text, field2::text, field3::text, field4::text,
       field5::text, field6::text, field7::text, field8::text, field9::text
FROM usertable
WHERE ycsb_key = ?;
```

Variant C: current YCSB JSONB read path

``` text
ResultSet.getString(field)
parseJsonArray(...)
joinArrayValue(...)
```

Expected confirmation:

-   Variant A stays flat.
-   Variant B shows the PostgreSQL detoast/serialization component.
-   Variant C is slower than B if client JSON parsing is a material contributor.

Falsifier:

-   Variant A, B, and C all behave similarly.

### Stage 4: TEXT\[\] Matched Control

Run a matched `TEXT[]` experiment using the same:

-   initial record count
-   extend count
-   Zipfian extend distribution
-   uniform read distribution
-   field length
-   outer epoch/inner run structure
-   vacuum policy

Collect the same instrumentation.

Compare:

-   main-run p95 by 10-epoch block
-   row-size distribution
-   heap size
-   TOAST size
-   WAL bytes/op
-   `tup_inserted/op`
-   buffer allocs/op
-   detoast-forcing probe time

Expected confirmation:

-   `TEXT[]` may grow and toast, but should show lower WAL/TOAST/internal tuple amplification per logical byte.
-   `TEXT[]` should show smoother p95 growth or weaker late p95 cliffs.

Falsifier:

-   `TEXT[]` shows the same TOAST growth, same late p95 cliffs, and same detoast/serialization profile under matched size.

### Stage 5: Vacuum Frequency Control

Run the JSONB workload under three vacuum policies:

-   current: `VACUUM (ANALYZE)` after every extend
-   reduced: vacuum every 10 iterations
-   none: no manual vacuum during the run

Keep autovacuum settings fixed and record them.

Expected confirmation:

-   If TOAST rewrite amplification is primary, all three variants should show size-linked degradation.
-   If per-cycle vacuum is amplifying the p95 spike, the 10-epoch bands should shift, weaken, or change shape when vacuum frequency changes.

Falsifier:

-   Removing per-cycle vacuum fully removes the late p95 spike while TOAST growth remains high. That would move vacuum/checkpoint perturbation from secondary to primary.

### Stage 6: Chunked JSONB Control

Implement a bounded-chunk JSONB variant:

``` sql
CREATE TABLE usertable (
  ycsb_key text PRIMARY KEY
);

CREATE TABLE usertable_jsonb_chunks (
  ycsb_key text NOT NULL,
  field_no int NOT NULL,
  chunk_no int NOT NULL,
  payload jsonb NOT NULL,
  PRIMARY KEY (ycsb_key, field_no, chunk_no)
);
```

Append to the current chunk until a size threshold, then create a new chunk. Suggested thresholds:

-   8 KB
-   32 KB
-   128 KB

Expected confirmation:

-   Smaller chunks bound per-update rewrite size.
-   WAL bytes/op and buffer allocs/op flatten relative to one giant JSONB array.
-   Main-run p95 loses the large late cliffs, especially for 8 KB and 32 KB chunks.

Falsifier:

-   Chunking does not reduce WAL, TOAST growth, or p95 spike shape.

### Stage 7: Normalized Append-Row Control

Implement an append-row model:

``` sql
CREATE TABLE usertable (
  ycsb_key text PRIMARY KEY
);

CREATE TABLE usertable_field_items (
  ycsb_key text NOT NULL,
  field_no int NOT NULL,
  item_no bigint NOT NULL,
  value text NOT NULL,
  PRIMARY KEY (ycsb_key, field_no, item_no)
);
```

`EXTEND` becomes an insert:

``` sql
INSERT INTO usertable_field_items (ycsb_key, field_no, item_no, value)
VALUES (?, ?, ?, ?);
```

Read can either:

-   fetch items as rows
-   aggregate to arrays
-   aggregate to JSONB with `jsonb_agg` only when needed

Expected confirmation:

-   Append cost becomes stable.
-   WAL/op becomes proportional to one inserted item, not to the full accumulated document.
-   Late main-run p95 cliffs should largely disappear unless read aggregation itself dominates.

Falsifier:

-   Append-row model still shows the same 10-epoch late p95 cliffs under row fetch reads.

## Minimal First Run

The minimum experiment that should give strong evidence is:

1.  Add Stage 1 storage instrumentation.
2.  Add Stage 2 detoast probes for min, p50, p95, p99, max keys.
3.  Rerun one JSON Blue-style run.
4.  Compare against one matched `TEXT[]` run with the same probes.

This is the fastest path to confirm:

-   whether TOAST size and dead TOAST churn explain the p95 spike
-   whether p95-sized keys have materially higher detoast cost
-   whether JSONB has a stronger amplification profile than `TEXT[]`

## Success Criteria

The TOAST amplification hypothesis is strongly confirmed if all of these hold:

-   TOAST relation size grows with epoch and tracks late p95.
-   Late p95-sized rows are physically toasted and much slower under detoast-forcing probes.
-   `tup_inserted/op`, `wal_bytes/op`, and `buffers_alloc/op` rise while logical `tup_updated/op` stays near 1.
-   Lookup-only probes remain cheap, but detoast/serialization probes become expensive.
-   `TEXT[]`, chunked JSONB, or normalized append rows reduce the cliff under comparable logical data growth.

## Decision Table

| Result | Interpretation | Next Action |
|------------------------|------------------------|------------------------|
| JSONB TOAST size and detoast probes track p95 | TOAST/read amplification confirmed | Build chunked JSONB and normalized controls |
| Vacuum policy changes spike shape heavily | Vacuum/checkpoint perturbation is important | Add more checkpoint/bgwriter metrics and tune vacuum/checkpoint schedule |
| Client JSON parsing dominates server detoast | Binding overhead contributes materially | Add a no-parse JSONB read mode for measurement |
| TEXT\[\] has same cliff at matched size | Problem is generic varlena/TOAST growth | Focus on chunking/normalization rather than JSONB-specific claims |
| Chunked JSONB removes cliff | Bounded rewrite size is sufficient | Use chunked JSONB as native-ish mitigation |
| Normalized rows remove cliff | Document rewrite is the root cause | Recommend relational append model for production |

## Notes For Writeup

Avoid saying `TEXT[]` does not TOAST. It can. The stronger and more accurate claim is:

> JSONB arrays and TEXT arrays both rewrite large varlena values on append, but JSONB has heavier binary-document rewrite, TOAST, server serialization, and client parsing costs. Under Zipfian append workloads, JSONB reaches a p95 cliff sooner and more sharply.

The writeup should distinguish:

-   logical update count: one YCSB `EXTEND`
-   PostgreSQL heap update: one new row version
-   TOAST writes: many internal chunks
-   read lookup cost: primary-key index scan
-   read materialization cost: detoast, deserialize/serialize, client parsing