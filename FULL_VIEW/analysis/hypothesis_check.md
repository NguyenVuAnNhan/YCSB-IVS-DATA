# FULL_VIEW Hypothesis Check

Data: - `full_view_run1` from `43.220.1.203` - `full_view_run2_3_106_232_96` from `3.106.232.96`

Both runs exited with status 0 and have 402 phase deltas. PostgreSQL is 16.11 in both runs. `pg_stat_io` is available; `pg_stat_checkpointer` is expected-unavailable on PG16 and checkpoint fields fall back to `pg_stat_bgwriter`.

## Verdict

The data supports the main working hypothesis: as logical value size grows, PostgreSQL pain is dominated by TOAST/WAL/buffer churn rather than heap/index lookup cost. The new observability modules materially helped identify that mechanism. They also show what did not explain the result: HOT update collapse, dead tuples, and statement-level tracing are not the main story in these runs.

## Key Evidence

Extend phases, median across the two runs:

| epoch | p99 ms | throughput ops/s | WAL bytes/op | TOAST blocks/op | TOAST read ratio | pg_stat_io evictions |
|----------:|----------:|----------:|----------:|----------:|----------:|----------:|
| 1 | 4.909 | 812.6 | 2604 | 3.4 | 0.000 | 0 |
| 50 | 56.383 | 182.1 | 196519 | 254.9 | 0.081 | 1858280 |
| 100 | 118.399 | 87.9 | 427339 | 486.0 | 0.080 | 3809020 |

Read phases after each extend, median across the two runs:

| epoch | p99 ms | throughput ops/s | TOAST blocks/op | TOAST read ratio | pg_stat_io evictions |
|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|
| 1 | 0.201 | 15504.5 | 0.6 | 0.000 | 0 |
| 50 | 3.098 | 2055.7 | 14.5 | 0.010 | 20459 |
| 100 | 7.581 | 1024.5 | 21.2 | 0.019 | 41763 |

Reference reads stay flat and do not touch TOAST:

| epoch | p99 ms | throughput ops/s | TOAST blocks/op |
|------:|-------:|-----------------:|----------------:|
|     1 |  0.141 |          19470.0 |             0.0 |
|    50 |  0.363 |          18431.9 |             0.0 |
|   100 |  0.671 |          16967.4 |             0.0 |

## Module Assessment

-   `pg_stat_io`: useful for count-level I/O and eviction evidence. It showed extend evictions rising from \~0 to \~3.8M per phase, and read-phase evictions rising into the tens of thousands. Limitation: `track_io_timing=off`, so read/write/fsync time columns are zero.
-   `pg_statio_user_tables`: essential. It separates heap/index/TOAST/TOAST-index touches and shows the useful cache-hit story: extend TOAST read ratio rises to \~8%, read phases stay mostly cached but still climb to \~2% TOAST misses at high value size.
-   `pg_buffercache` relation/page identity: very useful, but expensive. The page identity files are multi-GB and prove that `before_run` is essentially the same page set as `after_vacuum`; read phases then add many more TOAST pages. This is stronger than relation-level residency alone.
-   `pg_freespacemap`: useful supporting evidence. It shows vacuum leaves very large free space in the TOAST heap: by epoch 100 the median estimated TOAST free space before the read phase is about 28 GB, with most sampled TOAST pages more than half free.
-   `pg_stat_statements`: did not help in these runs because it was not loaded through `shared_preload_libraries`.
-   `pg_walinspect`: did not help here because WAL range inspection was not enabled; the WAL stats files only have headers.

## Hypothesis Outcomes

-   Value-size growth increases hidden work: supported strongly. Extend p99 rises from \~5 ms to \~118 ms while WAL/op rises from \~2.6 KB to \~427 KB and TOAST blocks/op from \~3.4 to \~486.
-   TOAST dominates once values grow: supported. TOAST storage fraction is \~0.98 by epoch 10 and \~0.998 by epoch 100.
-   Read pain is driven by larger TOAST working set and buffer churn: supported. Read p99 rises from \~0.2 ms to \~7.6 ms, reference reads stay around \~0.1-0.7 ms, and TOAST blocks/op rises from \~0.6 to \~21.
-   Checkpoints/bgwriter contribute write pressure but are not the main read-latency explanation. Extend p99 correlates with checkpoint write time because both grow with phase size; read p99 has weak checkpoint correlation but strong TOAST/buffer correlation.
-   HOT-update collapse is not supported. HOT update ratio rises toward \~0.998 in extend phases; heap/index costs are nearly flat relative to TOAST.
-   Dead tuples are not the main mechanism. After vacuum, `n_dead_tup_after` remains small relative to operations and does not track p99 as strongly as TOAST/WAL/buffer metrics.

## Caveats

-   These are two EC2 runs, not a full statistical campaign.
-   `track_io_timing=off`; enable it in a follow-up if we want latency attribution inside PostgreSQL I/O timing columns.
-   Page identity capture worked, but it is very large. Keep it focused on selected epochs/events for future long runs.
-   Enable `pg_stat_statements` via `shared_preload_libraries` only if statement-level timing matters; it is not needed for the main TOAST/cache conclusion.
-   Enable `--inspect-wal-ranges` only for a targeted WAL deep dive.