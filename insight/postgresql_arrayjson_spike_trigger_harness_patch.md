# PostgreSQL ArrayJSON Spike Trigger Harness Patch

## Goal

The current TOAST run confirms the broad mechanism behind the late p95 latency spike:

-   Zipfian JSONB appends grow a skewed set of large values.
-   PostgreSQL stores and rewrites those values through TOAST.
-   Reads increasingly pay detoast and JSONB serialization cost.
-   Vacuum/checkpoint/writeback/cache effects likely amplify the tail.

What remains unexplained is the exact timing and height of the recurring peaks, especially the roughly `12-13` epoch spacing and the epoch `97` overshoot.

The next harness patch should collect time-aligned sub-epoch data so we can distinguish:

-   large-key sampling
-   PostgreSQL shared-buffer or OS page-cache misses
-   checkpoint/writeback pressure
-   vacuum side effects
-   server-side detoast/serialization CPU
-   client-side JSON parsing/conversion cost

## Required Resolution

Epoch-level phase summaries are too coarse. The patch should collect:

-   `1s` samples during `extend`, `VACUUM`, `run`, `reference`, `clean-run`, and `avg-run`
-   operation-level or sampled-operation read traces during `run`
-   exact timestamps for phase boundaries, vacuum start/end, checkpoint observations, and probe execution

Minimum useful focus windows:

-   epochs `45-50`
-   epochs `56-61`
-   epochs `68-73`
-   epochs `81-86`
-   epochs `94-99`

These windows cover the five detected p95 peaks: `48`, `59`, `71`, `84`, and `97`.

## New Output Files

Recommended directory:

``` text
analysis/Data/Internal_data/toast_spike_trigger/
```

Recommended files per benchmark run:

``` text
postgresql_arrayjson_<run_name>_phase_timeline.csv
postgresql_arrayjson_<run_name>_pg_1s.csv
postgresql_arrayjson_<run_name>_os_1s.csv
postgresql_arrayjson_<run_name>_read_sample.csv
postgresql_arrayjson_<run_name>_slow_read_sample.csv
postgresql_arrayjson_<run_name>_checkpoint_observations.csv
postgresql_arrayjson_<run_name>_vacuum_progress_1s.csv
postgresql_arrayjson_<run_name>_buffer_residency.csv
postgresql_arrayjson_<run_name>_detoast_probe_sampled_keys.log
```

## 1. Phase Timeline

Write a row for every major phase boundary.

File:

``` text
postgresql_arrayjson_<run_name>_phase_timeline.csv
```

Columns:

``` text
run_name
epoch
phase
event
timestamp_unix_ms
timestamp_iso
record_count
operation_count
request_distribution
field_length
notes
```

Events:

``` text
load_start
load_end
extend_start
extend_end
vacuum_start
vacuum_end
run_start
run_end
reference_start
reference_end
clean_load_start
clean_load_end
clean_run_start
clean_run_end
avg_load_start
avg_load_end
avg_run_start
avg_run_end
backup_start
backup_end
probe_start
probe_end
```

Purpose:

-   Align all PostgreSQL, OS, and read-sample data to exact phase timing.
-   Check whether p95 peaks occur immediately after long vacuum/checkpoint/writeback intervals.

## 2. PostgreSQL 1-Second Sampler

Sample PostgreSQL state every `1s` during each phase.

File:

``` text
postgresql_arrayjson_<run_name>_pg_1s.csv
```

Columns:

``` text
run_name
epoch
phase
timestamp_unix_ms
numbackends
xact_commit
xact_rollback
blks_read
blks_hit
tup_returned
tup_fetched
tup_inserted
tup_updated
tup_deleted
temp_files
temp_bytes
deadlocks
wal_records
wal_fpi
wal_bytes
wal_buffers_full
checkpoints_timed
checkpoints_req
checkpoint_write_time
checkpoint_sync_time
buffers_checkpoint
buffers_clean
buffers_backend
buffers_backend_fsync
buffers_alloc
maxwritten_clean
stats_reset
```

Prefer cumulative counters plus derived deltas in analysis, not in the harness.

Purpose:

-   Detect whether p95 peaks align with checkpoint write/sync bursts.
-   Detect whether block reads, temp bytes, WAL, or buffer allocation spike inside the read phase rather than only across the whole epoch.

## 3. PostgreSQL Wait Event Sampler

Add current backend/wait-state sampling every `1s`.

This can be included in `pg_1s.csv` as aggregate counts or written separately.

Suggested aggregate columns:

``` text
active_backends
idle_backends
wait_client_count
wait_io_count
wait_lock_count
wait_lwlock_count
wait_timeout_count
wait_activity_count
wait_bufferpin_count
wait_extension_count
top_wait_events_json
```

Query source:

``` sql
SELECT
  state,
  wait_event_type,
  wait_event,
  count(*)
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event;
```

Purpose:

-   Separate CPU-bound JSONB/detoast work from IO waits or checkpoint/writeback waits.

## 4. OS 1-Second Sampler

Collect OS-level pressure every `1s`.

File:

``` text
postgresql_arrayjson_<run_name>_os_1s.csv
```

Columns:

``` text
run_name
epoch
phase
timestamp_unix_ms
cpu_user_pct
cpu_system_pct
cpu_iowait_pct
cpu_idle_pct
mem_available_kb
mem_dirty_kb
mem_writeback_kb
pgpgin_per_s
pgpgout_per_s
pswpin_per_s
pswpout_per_s
device
r_s
w_s
rkB_s
wkB_s
rrqm_s
wrqm_s
await_ms
r_await_ms
w_await_ms
aqu_sz
util_pct
```

Implementation options:

-   `iostat -x 1`
-   `/proc/meminfo`
-   `/proc/vmstat`
-   `/proc/diskstats`
-   existing watcher process, extended beyond CPU/memory

Purpose:

-   Confirm whether p95 peaks coincide with disk latency, queueing, dirty-page writeback, or iowait.

## 5. Read Operation Sampling

The current phase metrics do not tell us which keys were read during a spike. Add sampled read traces in the ArrayJSON read path.

File:

``` text
postgresql_arrayjson_<run_name>_read_sample.csv
```

Sample strategy:

-   log every read for small runs, or
-   sample `1/N` reads, for example `1/100`, plus always log slow reads above a threshold.

Columns:

``` text
run_name
epoch
phase
timestamp_unix_ms
operation_index
ycsb_key
key_size_bytes
latency_us
status
thread_id
fields_read
result_bytes_estimate
```

Add a separate slow-read file:

``` text
postgresql_arrayjson_<run_name>_slow_read_sample.csv
```

Slow-read threshold:

``` text
latency_us >= max(1000, rolling_p95_estimate)
```

Purpose:

-   Test whether p95 peaks are caused by larger sampled keys, hot keys, or specific outlier rows.
-   Link operation latency directly to key size.

## 6. Sampled-Key Detoast Probes

The existing deterministic detoast probe is useful, but it probes distribution quantiles, not necessarily the keys read during a spike.

Patch:

-   collect top slow keys from `slow_read_sample.csv`
-   run detoast probes on those keys after the run phase
-   also probe matched fast keys from the same epoch

File:

``` text
postgresql_arrayjson_<run_name>_detoast_probe_sampled_keys.log
```

Probe variants:

``` sql
-- A. key-only lookup
EXPLAIN (ANALYZE, BUFFERS)
SELECT ycsb_key
FROM usertable
WHERE ycsb_key = '<key>';

-- B. raw row lookup
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM usertable
WHERE ycsb_key = '<key>';

-- C. force JSONB materialization and serialization
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

Purpose:

-   Check whether actual slow reads are slow because of TOAST/detoast cost.
-   Distinguish key-only lookup cost from materialization/serialization cost.

## 7. Checkpoint Observations

PostgreSQL does not expose every checkpoint phase in one simple view, so capture counter changes and logs.

File:

``` text
postgresql_arrayjson_<run_name>_checkpoint_observations.csv
```

Columns:

``` text
run_name
epoch
phase
timestamp_unix_ms
checkpoints_timed
checkpoints_req
checkpoint_write_time
checkpoint_sync_time
buffers_checkpoint
buffers_clean
buffers_backend
maxwritten_clean
wal_bytes
wal_records
```

Also enable PostgreSQL checkpoint logging if possible:

``` conf
log_checkpoints = on
```

Purpose:

-   Test the `12-13` epoch rhythm against actual checkpoint/writeback behavior.

## 8. Vacuum Progress Sampler

Vacuum duration is currently known, but its internal progress is not.

File:

``` text
postgresql_arrayjson_<run_name>_vacuum_progress_1s.csv
```

Sample during `VACUUM (ANALYZE)`:

``` sql
SELECT
  pid,
  datname,
  relid::regclass AS relation,
  phase,
  heap_blks_total,
  heap_blks_scanned,
  heap_blks_vacuumed,
  index_vacuum_count,
  max_dead_tuples,
  num_dead_tuples
FROM pg_stat_progress_vacuum;
```

Columns:

``` text
run_name
epoch
timestamp_unix_ms
relation
phase
heap_blks_total
heap_blks_scanned
heap_blks_vacuumed
index_vacuum_count
max_dead_tuples
num_dead_tuples
```

Purpose:

-   Determine whether certain vacuum phases precede p95 peaks.
-   Check whether vacuum scans or cleanup are displacing useful TOAST/cache pages.

## 9. Buffer Residency Snapshots

If `pg_buffercache` is available, snapshot relation residency before and after major phases.

File:

``` text
postgresql_arrayjson_<run_name>_buffer_residency.csv
```

Query:

``` sql
SELECT
  now() AS ts,
  c.relname,
  count(*) AS buffers,
  count(*) * current_setting('block_size')::int AS bytes
FROM pg_buffercache b
JOIN pg_class c ON c.relfilenode = b.relfilenode
WHERE c.relname IN (
  'usertable',
  '<toast_table_name>',
  '<toast_index_name>'
)
GROUP BY c.relname;
```

Columns:

``` text
run_name
epoch
phase
event
timestamp_unix_ms
relation_name
buffers
bytes
```

Events:

``` text
before_extend
after_extend
after_vacuum
before_run
after_run
```

Purpose:

-   Test cache eviction/rewarming as the immediate spike trigger.

## 10. Client-Side Parse Timing

The JDBC/YCSB path may add JSON parsing/conversion cost after PostgreSQL returns the row.

Patch the ArrayJSON read method to split timings:

``` text
query_execute_us
resultset_fetch_us
json_parse_us
value_join_us
total_read_us
```

Add these fields to sampled read files when feasible.

Purpose:

-   Separate PostgreSQL detoast/serialization from Java JSON parsing and YCSB value conversion.

## Implementation Notes

### Sampling Threads

Use separate sampler processes/threads that write append-only CSV rows. Each sampler should include:

``` text
run_name
epoch
phase
timestamp_unix_ms
```

Avoid post-hoc alignment by filename only. Timestamps are the source of truth.

### Flush Behavior

Flush sample files periodically, but avoid flushing on every operation unless the sample rate is low. For operation samples:

-   buffer rows in memory
-   flush every `1s` or every `1000` rows
-   always flush at phase end

### Overhead Control

Default sample rates:

``` text
pg sampler: 1s
os sampler: 1s
read sample: 1/100 reads
slow-read sample: all reads >= threshold
detoast probes: top 10 slow keys + 10 matched fast keys per selected epoch
buffer residency: phase boundaries only
```

For peak-focused reruns, increase read sampling around known windows:

``` text
epochs 45-50, 56-61, 68-73, 81-86, 94-99: 1/10 reads or all reads if affordable
```

## Expected Confirmation Patterns

### If checkpoint/writeback is the trigger

We should see:

-   `checkpoint_write_time` or `checkpoint_sync_time` deltas rising inside or just before peak `run`
-   OS `await_ms`, `aqu_sz`, `util_pct`, or `cpu_iowait_pct` rising at the same timestamps
-   p95 peaks recurring near checkpoint counter changes

### If cache eviction/rewarming is the trigger

We should see:

-   lower TOAST buffer residency before peak `run`
-   higher shared/local reads or OS reads during peak
-   slow reads improving later in the same run phase as cache warms

### If key sampling is the trigger

We should see:

-   peak epochs sample more p95/p99/max-size keys
-   slow reads correspond to larger key sizes
-   fast reads in the same epoch correspond to smaller keys

### If server-side detoast/serialization is the trigger

We should see:

-   key-only probes stay cheap
-   JSONB serialization probes on slow keys are expensive
-   PostgreSQL wait events show CPU or buffer activity rather than IO waits

### If client-side parsing is the trigger

We should see:

-   PostgreSQL probes are not slow enough to explain total latency
-   `json_parse_us` or `value_join_us` dominates sampled slow reads

## Bottom Line

The current data identifies TOAST/value-size amplification as the root cause, but not the final trigger behind the sharp recurring peaks. This patch adds the missing sub-epoch evidence: exact phase timing, 1-second PostgreSQL and OS pressure, sampled read key/latency pairs, sampled-key detoast probes, vacuum progress, checkpoint observations, and buffer residency snapshots.

The critical resolution is:

-   `1s` for system and PostgreSQL samplers
-   operation-level or sampled-operation rows for reads
-   phase-boundary snapshots for relation/cache state