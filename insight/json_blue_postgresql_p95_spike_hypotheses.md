# JSON Blue PostgreSQL P95 Spike Hypotheses

## Scope

This note summarizes hypotheses for the anomalous late-epoch p95 latency spike in the JSON Blue PostgreSQL ArrayJSON big-cache runs:

-   `JSON_BLUE/postgresql_arrayjson_vacuum_notfull_bigcache_run3_zipfian_heavy_pure.csv`
-   `JSON_BLUE/postgresql_arrayjson_vacuum_notfull_bigcache_run4_zipfian_heavy_pure.csv`
-   `JSON_BLUE/postgresql_arrayjson_vacuum_notfull_bigcache_run5_zipfian_heavy_pure.csv`
-   `JSON_BLUE/postgresql_arrayjson_vacuum_notfull_bigcache_run6_zipfian_heavy_pure.csv`

The workload repeatedly performs a Zipfian `EXTEND` phase against JSONB fields, runs `VACUUM (ANALYZE)`, then executes a read-only main `run` phase.

## Key Observations

-   The late main `run` p95 spike appears in all four runs.
-   Last-10-epoch main `run` p95 means are approximately:
    -   run3: `1,470 us`
    -   run4: `1,752 us`
    -   run5: `1,562 us`
    -   run6: `1,387 us`
-   The `reference` phase remains near `46-56 us` p95 late in the benchmark, so the spike is not simply a host-wide slowdown.
-   By the final value-size snapshots in run4-run6, row sizes are highly skewed:
    -   mean row size: about `101 KB`
    -   p95 row size: about `150 KB`
    -   p99 row size: about `335-342 KB`
    -   max row size: about `38 MB`
-   By `Run100`, more than 5% of rows exceed `128 KB`, meaning p95 reads increasingly sample rows that are large enough to require substantial detoast/reconstruction work.
-   Extend-phase internals show strong storage amplification:
    -   `tup_updated/op` stays close to `1.00`
    -   `tup_inserted/op` rises from about `8.3` to `136`
    -   `wal_bytes/op` rises from about `24 KB` to `445 KB`
    -   `buffers_alloc/op` rises from about `0.39` to `41`
-   Query plans remain primary-key index scans, so the issue is not obviously a plan-shape regression.

## Ranked Hypotheses

### 1. TOAST chunk amplification is the primary driver

Each Zipfian `EXTEND` appends to a JSONB array. PostgreSQL cannot append in place inside a large JSONB datum. It creates a new heap tuple version and, once the value is large enough, rewrites out-of-line TOAST chunks.

The sharp rise in `tup_inserted/op` despite stable logical `tup_updated/op` is consistent with many internal TOAST rows being created per logical extend. The matching rise in WAL, buffer allocation, and checkpoint write pressure supports the same mechanism.

### 2. P95 jumps when the top 5% of reads cross large-value thresholds

The main `run` phase is read-only, but it reads rows that have been enlarged by prior Zipfian extends. Once at least 5% of rows are large enough, p95 begins to represent genuinely expensive reads: fetching the heap tuple, following TOAST pointers, reading many TOAST chunks, detoasting JSONB, and converting values back through the JDBC/YCSB path.

This explains why average latency rises steadily while p95 becomes much more visibly spiky in late epochs.

### 3. Main run has extra physical-history cost beyond value size alone

`clean-run` and `avg-run` also degrade, showing that large JSONB values alone are enough to hurt reads. However, the main `run` exceeds the clean/avg control mean late in the benchmark.

That gap suggests physical history matters too: repeated updates may leave scattered TOAST chunks, heap/TOAST bloat before cleanup, worse locality, and more buffer churn than a freshly loaded control table with similar average value size.

### 4. Per-cycle VACUUM becomes a perturbation as TOAST grows

The script runs `VACUUM (ANALYZE)` after every extend. In run4-run6, vacuum time grows from about `1s` early to roughly `600-700s` late.

The growing vacuum duration is probably another symptom of the same table/TOAST growth, but it may also perturb the following read phase through cache displacement, dirty-page writeback, visibility-map churn, and checkpoint interaction.

### 5. Checkpoint and background write pressure amplify the tail

Late epochs show much higher WAL and buffer allocation work per operation. PostgreSQL must eventually write those dirty pages and WAL-backed changes. Even though the main phase is read-only, it follows an expensive update/vacuum cycle, so reads may collide with background writeback and checkpoint effects.

This is a secondary hypothesis: the counters support pressure, but the strongest direct evidence still points to value/TOAST amplification.

## Less Likely Explanations

-   Planner regression: sampled plans remain primary-key index scans.
-   Deadlocks: deadlock counters stay at zero.
-   WAL buffer saturation as the direct cause: `wal_buffers_full` does not track p95 as strongly as value-size, block-read, WAL-byte, and buffer-allocation metrics.
-   General host slowdown: the `reference` phase remains comparatively flat.

## Suggested Confirmations

-   Measure heap and TOAST relation sizes by epoch with `pg_total_relation_size`, `pg_relation_size`, and toast table size.
-   Capture `pg_stat_user_tables` and `pg_stat_all_tables` for `n_dead_tup`, `n_live_tup`, `n_tup_hot_upd`, and vacuum counters.
-   Use `pgstattuple` or equivalent bloat checks on both heap and TOAST relations.
-   Compare `EXPLAIN (ANALYZE, BUFFERS)` for small, p95-sized, p99-sized, and max-sized keys.
-   Force detoast in the plan check, for example by selecting `octet_length(field0::text) + ...`, because `SELECT *` may not expose the full client-side detoast/conversion cost.
-   Test a variant with fewer or no per-cycle vacuums to separate vacuum perturbation from accumulated JSONB/TOAST growth.
-   Test a normalized append table design to avoid rewriting the whole JSONB value on every extend.

## Bottom Line

The most plausible explanation is that Zipfian JSONB extends create a small set of very large, repeatedly rewritten rows. PostgreSQL stores and rewrites those values through TOAST, which drives internal tuple inserts, WAL, buffer churn, and later read amplification. The late p95 spike appears when enough read requests hit these enlarged rows that detoast and scattered storage access move into the 95th percentile.