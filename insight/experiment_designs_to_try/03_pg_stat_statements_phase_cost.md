# pg_stat_statements Phase Cost

## Question

Does the normalized read query become more expensive inside PostgreSQL as TOAST values grow, and do VACC and NOVACC differ in average server-side buffer and I/O cost?

## Design

Use `pg_stat_statements` for per-phase aggregate query-cost snapshots. This complements operation-level `read_sample` and slow-read logs, but it does not replace them because it aggregates normalized statements and can hide a small tail subset.

## Setup

`pg_stat_statements` requires preload:

```sql
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET pg_stat_statements.track = 'all';
ALTER SYSTEM SET track_io_timing = on;
```

Restart PostgreSQL after changing `shared_preload_libraries`, then:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

## Capture Schedule

For each major phase, reset before phase start and snapshot after phase end:

```text
extend_start -> reset
extend_end -> snapshot
vacuum_start -> optional snapshot/reset boundary
run_start -> reset
run_end -> snapshot
reference_start -> reset
reference_end -> snapshot
clean-run_start -> reset
clean-run_end -> snapshot
avg-run_start -> reset
avg-run_end -> snapshot
```

If resets are too invasive for concurrent phases, use timestamped snapshots and compute deltas offline.

## Output

Suggested file:

```text
${RUN_NAME}_pg_stat_statements.csv
```

Suggested columns:

```text
run_name
epoch
phase
event
timestamp_unix_ms
userid
dbid
queryid
calls
total_exec_time
mean_exec_time
max_exec_time
stddev_exec_time
rows
shared_blks_hit
shared_blks_read
shared_blks_dirtied
shared_blks_written
blk_read_time
blk_write_time
temp_blks_read
temp_blks_written
wal_records
wal_bytes
query
```

## Query Shape

```sql
SELECT
  userid,
  dbid,
  queryid,
  calls,
  total_exec_time,
  mean_exec_time,
  max_exec_time,
  stddev_exec_time,
  rows,
  shared_blks_hit,
  shared_blks_read,
  shared_blks_dirtied,
  shared_blks_written,
  blk_read_time,
  blk_write_time,
  temp_blks_read,
  temp_blks_written,
  wal_records,
  wal_bytes,
  query
FROM pg_stat_statements
WHERE query ILIKE '%usertable%'
ORDER BY total_exec_time DESC;
```

## Analysis

Track per-call metrics:

```text
shared_blks_read_per_call
shared_blks_hit_per_call
total_exec_time_per_call
blk_read_time_per_call
wal_bytes_per_call
```

Compare against:

- p95 latency
- run-phase `blks_read` deltas
- page-identity churn
- VACC vs NOVACC late-epoch differences

## Limits

`pg_stat_statements` does not provide p95 latency, exact page identity, or key-specific behavior. It is best used as aggregate server-side corroboration.

