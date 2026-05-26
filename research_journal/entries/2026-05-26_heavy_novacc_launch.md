# Heavy NOVACC Launch

- Date: 2026-05-26
- Workspace: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`
- Related repo: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`
- Status: running

## Context

This entry records the launch of the heavy NOVACC baseline from the remaining experiment plan. This run is the vacuum-off counterpart to the heavy VACC full-view baseline and is intended to test whether removing the explicit vacuum phase materially changes WAL volume, dead tuples, free-space behavior, TOAST block touches, cache residency, and tail latency.

## Host And Preflight

- EC2 host: `13.236.86.169`
- Remote hostname: `ip-172-31-13-109`
- SSH login: `ubuntu`
- Benchmark OS user: `ycsb` via `sudo -u ycsb`
- PostgreSQL version: `16.11`
- Disk before launch: about 449 GB free on `/`
- Existing benchmark tmux session before launch: none
- Direct SSH as `ycsb`: denied by public key, so launch used the established `ubuntu` to `sudo -u ycsb` path.

Preflight found all required extension packages available. The server initially had `shared_preload_libraries` empty and `track_io_timing=off`, so the host was updated before launch:

- `shared_preload_libraries=pg_stat_statements`
- `track_io_timing=on`
- `log_checkpoints=on`
- PostgreSQL restarted successfully and accepted connections afterward.

A reset/permission smoke test created a temporary database and confirmed that `ycsb` could create and query:

- `pg_buffercache`
- `pg_freespacemap`
- `pg_stat_statements`
- `pg_walinspect`
- `pg_prewarm`

## Run Settings

- Run id: `full_view_heavy_novacc_run1`
- Launcher: `/home/ycsb/run_full_view_heavy_novacc_run1.sh`
- tmux session: `ycsb`
- Run directory: `/home/ycsb/ycsb-ec2-bundle/experiment_scripts/benchruns/full_view_heavy_novacc_run1`
- Database: `full_view_novacc`
- Reference database: `full_view_novacc_unchange`
- Backup database: `full_view_novacc_backup`
- Scale: `heavy`
- Starting records: 10,000
- Operations per run phase: 100,000
- Extend operations per extend phase: 100,000
- Epochs: 10
- Runs per epoch: 10
- Extend distribution: zipfian
- Read distribution: uniform
- Workload: pure read after extend
- Vacuum: off, `VACUUM_ENABLED=0`
- Full visibility required: yes
- Sample interval: 5 seconds
- Relation-size sample interval: 30 seconds

## Early Observations

The run started at 2026-05-26T09:26:23Z. It passed full-visibility prerequisites for `full_view_novacc` and `full_view_novacc_unchange`, completed the initial load phase for both databases, and then entered `full_view_novacc_extend_1`. The continuous sampler was active during the first extend phase.

Early files confirmed present:

- `manifest.json`
- `config_resolved.json`
- `heartbeat.log`
- `stdout.log`
- `stderr.log`
- `sql/preflight.json`
- `sql/pg_settings.csv`
- `sql/postgres_version.txt`
- `sql/relation_mapping.csv`
- `samples/pg_stat_io.csv`
- `samples/pg_stat_database.csv`
- `samples/pg_stat_user_tables.csv`
- `samples/pg_statio_user_tables.csv`
- `samples/pg_stat_user_indexes.csv`
- `samples/pg_stat_wal.csv`
- `samples/pg_stat_bgwriter.csv`
- `samples/pg_stat_activity_waits.csv`
- `samples/relation_sizes.csv`
- `samples/os_process_top.csv`
- `samples/vmstat.log`
- `samples/iostat.log`
- `snapshots/lsn_markers.csv`
- load-phase before/after snapshots
- `ycsb/full_view_novacc_load_0.out`

`pg_stat_io` is available on this PostgreSQL 16 host. `pg_stat_checkpointer` is expected to be unavailable until PostgreSQL 17, so checkpoint interpretation should use `pg_stat_bgwriter` fallback columns where available.

Latest launch check:

- tmux session `ycsb` was still active.
- Active phase: `full_view_novacc_extend_1`.
- Disk remained healthy at about 457 GB free on `/`.
- Heartbeat had advanced to 2026-05-26T09:27:23Z.

## Next Actions

- Monitor disk use and tmux output while the long run proceeds.
- After completion, pull the run directory into `YCSB-IVS-DATA`.
- Verify manifest, samples, snapshots, YCSB outputs, derived metrics, and `derived/summary.md`.
- Compare against the heavy VACC baseline using normalized metrics rather than raw counters alone.
