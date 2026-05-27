# FULL_VIEW VACC Runs Backfill

- Date: 2026-05-28
- Workspace: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`
- Related repo: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`
- Status: complete

## Context

This entry backfills the two FULL_VIEW heavy VACC runs that were already pulled into the data workspace but were not yet recorded in the research journal:

- `FULL_VIEW/full_view_run1`
- `FULL_VIEW/full_view_run2_3_106_232_96`

These runs are the vacuum-enabled full-observability baseline pair used before the later NOVACC run. They are useful as evidence about the main PostgreSQL pain mechanism, but they are not a perfectly clean same-host comparison against the newer NOVACC run.

## Run Settings

Both runs used the same logical benchmark shape:

- Benchmark script: `experiment_postgresql_array_json.sh`
- Database: `full_view`
- Target table: `usertable`
- Scale: `heavy`
- Extend distribution: `zipfian`
- Read workload: `pure`
- Vacuum: enabled, `VACUUM_ENABLED=1`
- Epoch shape: `10 x 10`
- Extend operations per epoch: `100000`
- PostgreSQL: `16.11`
- `shared_buffers`: `4GB`
- `track_io_timing`: `off`
- `log_checkpoints`: `on`
- `shared_preload_libraries`: empty

`pg_stat_io`, `pg_buffercache`, `pg_freespacemap`, and `pg_stat_statements` were visible in preflight. `pg_stat_checkpointer` was unavailable, which is expected on PostgreSQL 16; checkpoint fields were taken from `pg_stat_bgwriter`.

## Run Artifacts

`full_view_run1`:

- Local path: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/FULL_VIEW/full_view_run1`
- EC2 public IP used at launch/pull time: `43.220.1.203`
- Manifest hostname: `ip-172-31-13-109`
- Start: `2026-05-19T13:37:31Z`
- End: `2026-05-20T22:53:15Z`
- Exit status: `0`

`full_view_run2`:

- Local path: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/FULL_VIEW/full_view_run2_3_106_232_96`
- EC2 public IP used at launch/pull time: `3.106.232.96`
- Manifest hostname: `ip-172-31-8-159`
- Start: `2026-05-19T13:54:36Z`
- End: `2026-05-20T18:14:06Z`
- Exit status: `0`
- This run used the default `ubuntu` user on the EC2 instance.

Derived analysis is under:

- `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/FULL_VIEW/analysis`

## Notes

The paired FULL_VIEW analysis supports the main working hypothesis: as JSONB values grow, hidden PostgreSQL work grows primarily through TOAST/WAL/buffer churn rather than ordinary heap or index lookup cost.

At epoch 100, the extend phase reached:

| run | p95 ms | p99 ms | throughput ops/s | WAL bytes/op | TOAST blocks/op | client backend relation evictions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_view_run1` | 63.231 | 122.431 | 83.362 | 424619 | 472.843 | 3793177 |
| `full_view_run2` | 57.311 | 114.367 | 92.366 | 430058 | 499.179 | 3824863 |

At epoch 100, the post-extend read phase reached:

| run | p95 ms | p99 ms | throughput ops/s | TOAST blocks/op | TOAST index blocks/op |
| --- | ---: | ---: | ---: | ---: | ---: |
| `full_view_run1` | 2.459 | 8.935 | 738.984 | 21.390 | 40.023 |
| `full_view_run2` | 2.157 | 6.227 | 1310.015 | 21.071 | 40.022 |

The unchanged reference read stayed much flatter and did not touch TOAST:

| run | reference epoch 100 p95 ms | reference epoch 100 p99 ms | reference TOAST blocks/op |
| --- | ---: | ---: | ---: |
| `full_view_run1` | 0.074 | 0.659 | 0 |
| `full_view_run2` | 0.059 | 0.682 | 0 |

The paired median view shows the phase change clearly. Extend p99 rose from about `4.91 ms` at epoch 1 to `118.40 ms` at epoch 100. Over the same selected epochs, WAL bytes/op rose from about `2604` to `427339`, TOAST blocks/op rose from about `3.44` to `486.01`, and client backend relation evictions rose from `0` to about `3.81M` per phase.

Read phases also grew with value size: median read p99 rose from about `0.20 ms` at epoch 1 to `7.58 ms` at epoch 100, while TOAST blocks/op rose from about `0.59` to `21.23`. Reference reads remained around `0.14-0.67 ms` p99 with zero TOAST blocks/op.

## Decisions

The FULL_VIEW/VACC pair should remain our main vacuum-enabled baseline evidence, but it should be used carefully:

- Extend-phase behavior is fairly repeatable across the two runs.
- Read-phase latency and throughput are less repeatable, even though TOAST block counts are very similar.
- `full_view_run2` is faster in the read phase than `full_view_run1`; this suggests host/runtime/cache differences matter and should not be overinterpreted as a workload logic difference.
- Because `track_io_timing=off` and `pg_stat_statements` was not preloaded, these runs support counter-level I/O and residency conclusions better than PostgreSQL-internal timing attribution.

The strongest interpretation is that the runs are consistent with the TOAST working-set and buffer-pressure mechanism. They do not prove that explicit vacuum is the cause of late read-tail latency. The later NOVACC run is therefore necessary and should be compared against these VACC results with the above caveats.

## Next Actions

- Use the FULL_VIEW/VACC pair as historical vacuum-enabled baseline evidence.
- Prefer the newer NOVACC run for vacuum-off evidence because it has a cleaner journal trail and targeted follow-up analysis.
- If we need a clean VACC versus NOVACC causal comparison, rerun Heavy VACC with the same host/settings discipline as the NOVACC run.
- Keep page-identity capture targeted; the FULL_VIEW page-identity data helped but is very large.
