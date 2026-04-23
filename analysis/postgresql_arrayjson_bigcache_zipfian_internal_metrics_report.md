# PostgreSQL ArrayJSON Bigcache Zipfian Heavy Pure Internal Metrics Report

## Scope

-   CSV inputs analyzed:

-   `JSON_BLUE/postgresql_arrayjson_vacuum_notfull_bigcache_run4_zipfian_heavy_pure.csv`

-   `JSON_BLUE/postgresql_arrayjson_vacuum_notfull_bigcache_run5_zipfian_heavy_pure.csv`

-   `JSON_BLUE/postgresql_arrayjson_vacuum_notfull_bigcache_run6_zipfian_heavy_pure.csv`

-   Repeated phases analyzed: `run`, `clean-run`, `avg-run`, `extend`, and `reference`.

-   The PostgreSQL counters are cumulative, so the analysis uses same-phase epoch deltas normalized by `Operations`.

## Executive Summary

-   `run` latency rises from `87.8` us to `703.0` us while throughput falls from `11,932.0` to `1,446.0` ops/sec.
-   The strongest long-run `run` signals are read amplification and write amplification together: tuples fetched/op, tuples returned/op, block reads/op, and WAL bytes/op all have very strong monotonic ties to performance decay.
-   `extend` is the clearest source phase: average latency grows from `1,659.9` us to `10,429.7` us while throughput collapses from `614.7` to `96.0` ops/sec.
-   During `extend`, logical updates stay near one per op, but internal tuple inserts and WAL bytes per op rise by large multiples, which is consistent with storage amplification as values grow.

## Phase Drift Summary

| Phase | Avg latency first10 us | Avg latency last10 us | Avg latency change % | Throughput first10 | Throughput last10 | Throughput change % |
|-----------|-----------|-----------|-----------|-----------|-----------|-----------|
| run | 87.81 | 702.96 | 709.6 | 11,932.00 | 1,445.99 | -87.8 |
| clean-run | 75.15 | 503.88 | 568.5 | 13,401.83 | 1,996.03 | -85.1 |
| avg-run | 71.79 | 525.30 | 630.0 | 13,796.14 | 1,903.10 | -86.2 |
| extend | 1,659.87 | 10,429.74 | 528.3 | 614.74 | 96.04 | -84.4 |
| reference | 37.38 | 43.49 | 16.2 | 24,068.56 | 21,077.58 | -12.5 |

## Top Drivers

| Phase     | Driver                          | Latency rho | Throughput rho |
|-----------|---------------------------------|-------------|----------------|
| run       | Tuples returned/op              | 0.991       | -0.991         |
| run       | Tuples fetched/op               | 0.991       | -0.991         |
| run       | WAL bytes/op                    | 0.991       | -0.991         |
| clean-run | WAL bytes/op                    | 0.998       | -0.998         |
| clean-run | WAL records/op                  | 0.998       | -0.998         |
| clean-run | Cache-hit ratio                 | 0.997       | -0.997         |
| avg-run   | WAL bytes/op                    | 0.997       | -0.997         |
| avg-run   | WAL records/op                  | 0.997       | -0.997         |
| avg-run   | Buffer allocs/op                | 0.996       | -0.995         |
| extend    | Tuples fetched/op               | 0.999       | -0.999         |
| extend    | Tuples returned/op              | 0.999       | -0.999         |
| extend    | Internal inserts/logical update | 0.999       | -0.999         |
| reference | Cache-hit ratio                 | -0.539      | 0.554          |
| reference | Backend buffers/op              | 0.532       | -0.547         |
| reference | Buffer allocs/op                | 0.531       | -0.545         |

Interpretation:

-   `run`, `clean-run`, and `avg-run` all point to the same family of degrading internals: more WAL per op, more buffer allocation churn, and more block work per logical operation.
-   `reference` is much flatter by comparison: average latency only moves from `37.4` us to `43.5` us, which makes it a useful control phase.
-   `clean-run` and `avg-run` remain severe, with throughput falling from `13,401.8` to `1,996.0` in `clean-run` and from `13,796.1` to `1,903.1` in `avg-run`.

## Extend Storage Amplification

| Run | Logical updates/op first10 | Logical updates/op last10 | Internal tuple inserts/op first10 | Internal tuple inserts/op last10 | Internal inserts/logical update first10 | Internal inserts/logical update last10 | WAL bytes/op first10 | WAL bytes/op last10 |
|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| 4 | 1.000 | 1.002 | 8.361 | 136.222 | 8.357 | 135.938 | 24,247.5 | 446,362.5 |
| 5 | 1.000 | 1.002 | 8.326 | 135.654 | 8.323 | 135.377 | 24,287.4 | 444,591.2 |
| 6 | 1.000 | 1.002 | 8.319 | 136.169 | 8.315 | 135.876 | 24,188.7 | 445,916.6 |

-   The important pattern is that `tup_updated_per_op` stays around one, but `tup_inserted_per_op` and `internal_inserts_per_logical_update` climb sharply late in the run.
-   Because these repeated workloads are not user-level insert workloads, that rising internal insert pressure is best interpreted as PostgreSQL doing more underlying storage work for each logical extend.

## Run-Phase Read Amplification

| Run | Tuples returned/op first10 | Tuples returned/op last10 | Tuples fetched/op first10 | Tuples fetched/op last10 | Block reads/op first10 | Block reads/op last10 | Block hits/op first10 | Block hits/op last10 | Cache-hit ratio first10 | Cache-hit ratio last10 |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| 4 | 28.41 | 341.97 | 27.64 | 341.06 | 0.00 | 120.43 | 94.82 | 727.77 | 1.000 | 0.889 |
| 5 | 28.32 | 339.86 | 27.56 | 338.96 | 0.00 | 117.74 | 94.57 | 727.59 | 1.000 | 0.893 |
| 6 | 28.25 | 342.11 | 27.49 | 341.18 | 0.00 | 118.02 | 94.39 | 735.97 | 1.000 | 0.889 |

-   In every analyzed run, tuples fetched/op and block reads/op rise substantially over time in `run`, which means the read path is paying for much larger or more fragmented state later in the benchmark.
-   Cache-hit ratio declines modestly rather than collapsing outright, so the dominant issue is not just cache failure; it is the growing amount of work done per logical read.

## Bottom Line

-   Yes: the internal metrics captured inside the CSVs strongly support the same story as the external watcher metrics, but with better causal detail.
-   The main driver is cumulative storage and write amplification during `extend`, which then shows up as much heavier read amplification in `run`, `clean-run`, and `avg-run`.
-   The most explanatory internal metrics here are `wal_bytes_per_op`, `wal_records_per_op`, `buffers_alloc_per_op`, `tup_fetched_per_op`, `tup_returned_per_op`, `blks_read_per_op`, and `internal_inserts_per_logical_update`.

## Generated Tables

-   `analysis/postgresql_arrayjson_bigcache_zipfian_internal_phase_drift.csv`
-   `analysis/postgresql_arrayjson_bigcache_zipfian_internal_driver_summary.csv`
-   `analysis/postgresql_arrayjson_bigcache_zipfian_internal_run_read_amplification.csv`
-   `analysis/postgresql_arrayjson_bigcache_zipfian_internal_extend_storage.csv`