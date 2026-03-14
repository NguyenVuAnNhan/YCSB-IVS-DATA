# Data Dictionary

This repository currently contains two raw CSV schema families under `DATA/`:

- PostgreSQL and `postgresql_array` files: 42 columns
- Neo4j files: 43 columns

`postgresql_array` uses the same raw schema as PostgreSQL.

## How To Read These Metrics

- Shared YCSB fields such as `Throughput(ops/sec)` and latency percentiles are per-row benchmark outputs.
- Many database-native fields behave like cumulative counters within a phase, not per-epoch deltas. For analysis, it is often more meaningful to difference them across epochs.
- A few database-native fields behave like gauges or snapshots rather than counters, especially concurrency-style metrics.
- Any field with units embedded in the name, such as `(ms)` or `(us)`, uses that unit directly. When a database-native field name includes `time` but no explicit unit, the raw CSV does not encode the unit in the column name; treat it as an exported DB time metric and confirm the exact unit against the collector if you need source-level precision.

## Shared Fields

These columns appear in both PostgreSQL-family and Neo4j CSVs unless noted otherwise.

| Column | Type | Unit | Meaning | Notes |
| --- | --- | --- | --- | --- |
| `Epoch` | integer | index | Sequential epoch number within a run/phase. | Used as the primary time axis in plots. |
| `Phase` | categorical | none | Benchmark phase label. | Common values in this repo include `load`, `run`, `extend`, `reference`, `clean-run`, and `avg-run`. |
| `Recordcount` | integer | records | Target record count seen by the workload at that row. | Often constant within a phase, except growth phases. |
| `Readallfields` | boolean | none | Whether YCSB reads the full record payload. | Workload configuration flag. |
| `Requestdist` | categorical | none | Request distribution used by the workload. | Common values are `uniform` and `zipfian`. |
| `Operation` | categorical | none | Primary operation represented by the row. | Common values include `READ`, `INSERT`, and `EXTEND`. |
| `Readprop` | numeric | fraction | Share of operations configured as reads. | Workload mix parameter. |
| `Updateprop` | numeric | fraction | Share of operations configured as updates. | Workload mix parameter. |
| `Scanprop` | numeric | fraction | Share of operations configured as scans. | Workload mix parameter. |
| `Insertprop` | numeric | fraction | Share of operations configured as inserts. | Workload mix parameter. |
| `Extendprop` | numeric | fraction | Share of operations configured as extend/growth operations. | Workload mix parameter. |
| `Runtime(ms)` | integer | ms | Runtime spent executing the row's benchmark batch. | YCSB-reported runtime. |
| `Throughput(ops/sec)` | numeric | ops/sec | Achieved throughput for the row. | Core performance metric. |
| `Operations` | integer | operations | Number of operations completed in the row. | Often used as a weight for aggregation. |
| `AverageLatency(us)` | numeric | us | Mean operation latency. | Core performance metric. |
| `MinLatency(us)` | integer | us | Minimum observed operation latency. | Tail-insensitive lower bound. |
| `MaxLatency(us)` | integer | us | Maximum observed operation latency. | Extreme tail value. |
| `95thPercentileLatency(us)` | integer | us | 95th percentile latency. | Tail latency metric. |
| `99thPercentileLatency(us)` | integer | us | 99th percentile latency. | More extreme tail latency metric. |
| `Return=OK` | integer | operations | Count of operations that returned success. | Present in both schema families. |
| `RETURN=ERROR` | integer | operations | Count of operations that returned error. | Neo4j schema only. PostgreSQL CSVs do not include this column. |

## PostgreSQL-Family Fields

These fields appear in PostgreSQL and `postgresql_array` CSVs.

| Column | Type | Unit | Meaning | Notes |
| --- | --- | --- | --- | --- |
| `blks_read` | counter | blocks | Shared-buffer blocks read from disk. | Usually cumulative within a phase. |
| `blks_hit` | counter | blocks | Shared-buffer blocks satisfied from cache. | Often paired with `blks_read` to form a cache-hit ratio. |
| `tup_returned` | counter | tuples | Rows returned by sequential or index scans. | Cumulative activity counter. |
| `tup_fetched` | counter | tuples | Rows fetched by row-oriented access paths. | Cumulative activity counter. |
| `tup_inserted` | counter | tuples | Rows inserted. | Cumulative write-volume counter. |
| `tup_updated` | counter | tuples | Rows updated. | Cumulative write-volume counter. |
| `tup_deleted` | counter | tuples | Rows deleted. | Cumulative write-volume counter. |
| `deadlocks` | counter | events | Deadlocks detected. | Usually low or zero in healthy runs. |
| `temp_files` | counter | files | Temporary files created. | Often indicates spill or sort/hash overflow activity. |
| `temp_bytes` | counter | bytes | Bytes written to temporary files. | Useful for spotting spill pressure. |
| `checkpoints_timed` | counter | events | Timed checkpoints completed. | Cumulative checkpoint counter. |
| `checkpoints_req` | counter | events | Requested checkpoints completed. | Cumulative checkpoint counter. |
| `buffers_checkpoint` | counter | buffers | Buffers written during checkpoints. | Cumulative background write metric. |
| `buffers_clean` | counter | buffers | Buffers written by the background writer. | Cumulative background write metric. |
| `buffers_backend` | counter | buffers | Buffers written directly by backend sessions. | Often rises when backends must absorb write work themselves. |
| `buffers_alloc` | counter | buffers | Buffers allocated from shared buffers. | Often used as a pressure/growth proxy. |
| `checkpoint_write_time` | counter | time metric | Time spent writing checkpoint buffers. | Column name does not encode the source unit, but PostgreSQL commonly exposes this as cumulative checkpoint time. |
| `checkpoint_sync_time` | counter | time metric | Time spent syncing checkpoint buffers. | Often analyzed alongside checkpoint write time. |
| `wal_bytes` | counter | bytes | Write-ahead log volume generated. | Useful for write amplification analysis. |
| `wal_records` | counter | records | WAL records generated. | Cumulative WAL activity counter. |
| `wal_fpi` | counter | records | Full-page images written to WAL. | Cumulative WAL overhead counter. |
| `wal_buffers_full` | counter | events | Times WAL buffers became full. | Can indicate WAL-side pressure. |

## Neo4j Fields

These fields appear in Neo4j CSVs.

| Column | Type | Unit | Meaning | Notes |
| --- | --- | --- | --- | --- |
| `page_cache_hits` | counter | events | Page cache hits. | Often paired with `page_cache_faults`. |
| `page_cache_faults` | counter | events | Page cache misses/faults. | Useful for cache-pressure analysis. |
| `transaction_commits` | counter | events | Transactions committed. | Cumulative transaction success counter. |
| `transaction_rollbacks` | counter | events | Transactions rolled back. | Cumulative transaction failure counter. |
| `nodes_created` | counter | nodes | Nodes created. | Cumulative write-volume counter. |
| `nodes_deleted` | counter | nodes | Nodes deleted. | Cumulative write-volume counter. |
| `relationships_created` | counter | relationships | Relationships created. | Cumulative write-volume counter. |
| `relationships_deleted` | counter | relationships | Relationships deleted. | Cumulative write-volume counter. |
| `properties_set` | counter | properties | Properties written or updated. | Cumulative write-volume counter. |
| `index_hits` | counter | events | Index lookups satisfied. | Cumulative index usage counter. |
| `index_misses` | counter | events | Index lookups missed. | Useful for diagnosing lookup efficiency. |
| `lock_acquisition_time` | metric | time metric | Time spent acquiring locks. | Unit is not encoded in the column name. |
| `lock_wait_time` | metric | time metric | Time spent waiting on locks. | Unit is not encoded in the column name. |
| `checkpoint_total_time` | counter | time metric | Total checkpoint time. | Usually cumulative across the run. |
| `checkpoint_total_events` | counter | events | Number of checkpoint events. | Cumulative checkpoint counter. |
| `log_rotation_events` | counter | events | Number of transaction-log rotations. | Cumulative logging counter. |
| `log_appended_bytes` | counter | bytes | Transaction-log bytes appended. | Useful for write amplification analysis. |
| `log_rotation_total_time` | counter | time metric | Total time spent rotating logs. | Unit is not encoded in the column name. |
| `transaction_started` | counter | events | Transactions started. | Cumulative transaction volume counter. |
| `transaction_peak_concurrent` | gauge | transactions | Peak concurrent transactions observed. | Snapshot-style concurrency metric rather than a pure counter. |
| `transaction_active` | gauge | transactions | Active transactions at sample time. | Snapshot-style concurrency metric. |
| `transaction_terminated` | counter | events | Transactions terminated. | Cumulative termination counter. |

## Derived Metrics Used In Analysis Reports

These are not collected directly in the raw CSVs, but the Quarto reports and analysis notebooks may derive them from the raw fields.

| Metric | Based on | Meaning |
| --- | --- | --- |
| `cache_hit_ratio` | PostgreSQL: `blks_hit / (blks_hit + blks_read)` | Fraction of buffer accesses served from cache. |
| `blk_reads_per_op` | `diff(blks_read) / Operations` | Disk block reads generated per benchmark operation in an epoch. |
| `blk_hits_per_op` | `diff(blks_hit) / Operations` | Cache hits generated per benchmark operation in an epoch. |
| `wal_bytes_per_op` | `diff(wal_bytes) / Operations` | WAL volume generated per benchmark operation in an epoch. |
| `wal_records_per_op` | `diff(wal_records) / Operations` | WAL records generated per benchmark operation in an epoch. |
| `buffer_alloc_per_op` | `diff(buffers_alloc) / Operations` | Buffer allocations generated per benchmark operation in an epoch. |
| `log10_throughput` | `log10(Throughput(ops/sec))` | Log-scaled throughput used to compare differently scaled phases on one visual axis. |

## Practical Notes

- If you are comparing epochs inside a phase, database-native counters usually need `diff()` first.
- If you are aggregating rows across operations or phases, `Operations` is the safest default weight.
- The most stable cross-database comparison fields are the shared YCSB performance outputs: throughput, operations, and latency percentiles.
