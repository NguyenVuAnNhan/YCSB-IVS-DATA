# Heavy pg_prewarm TOAST-Index Launch

- Date: 2026-05-28
- Workspace: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`
- Related repo: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`
- Status: active after relaunch

## Context

Launched the heavy `pg_prewarm` TOAST-index-only intervention requested for host `16.176.19.144`.

This run is intended to isolate whether warming the TOAST index alone changes late read-tail latency. It complements the already-active heap plus TOAST-index prewarm run on `3.104.54.25`.

## Notes

Host and login:

- Public IP: `16.176.19.144`
- Hostname: `ip-172-31-13-109`
- Login user: `ubuntu`
- Remote bundle: `/home/ubuntu/ycsb-ec2-bundle`
- tmux session: `ycsb`

Run settings:

- Current clean Run ID: `full_view_heavy_prewarm_toast_index_run3`
- Current launcher: `/home/ubuntu/run_full_view_heavy_prewarm_toast_index_run3.sh`
- Current remote run directory: `/home/ubuntu/ycsb-ec2-bundle/experiment_scripts/benchruns/full_view_heavy_prewarm_toast_index_run3`
- Failed early attempts preserved: `full_view_heavy_prewarm_toast_index_run1`, `full_view_heavy_prewarm_toast_index_run2`
- DB: `full_view_prewarm_toast_index`
- Unchanged DB: `full_view_prewarm_toast_index_unchange`
- Backup DB: `full_view_prewarm_toast_index_backup`
- Scale: `heavy`
- Epoch shape: `10 x 10`
- Record count: `10000`
- Operations per phase: `100000`
- Extend distribution: `zipfian`
- Read distribution: `uniform`
- Workload: `pure`
- Vacuum: enabled
- Full visibility: required
- Sampling: PostgreSQL/OS every `5s`; relation size every `30s`
- Intervention: `SPIKE_TRIGGER_PREWARM_ENABLED=1`, `SPIKE_TRIGGER_PREWARM_MODE=toast_index`

Preflight/environment observations:

- PostgreSQL `16.11`
- `shared_buffers=4GB`
- `shared_preload_libraries=pg_stat_statements`
- `track_io_timing=on`
- `log_checkpoints=on`
- `ycsb` database role has `rolcreatedb=true` and `rolsuper=true`
- Extension smoke passed in a temporary database for `pg_buffercache`, `pg_freespacemap`, `pg_prewarm`, `pg_stat_statements`, and `pg_walinspect`.
- Launch-time disk: `/` had about `117G` free. Existing `full_view_novacc` database was about `319G`; it was not modified or deleted.

Harness/dependency actions:

- Deployed current `experiment_postgresql_array_json.sh`, `benchmark_observability.py`, `run_postgresql_array_json_full_visibility.sh`, `watcher.sh`, and `README.md` into `/home/ubuntu/ycsb-ec2-bundle/experiment_scripts`.
- Deployed missing `jdbc-array-json` binding into `/home/ubuntu/ycsb-ec2-bundle/jdbc-array-json`.
- Updated remote `bin/ycsb.sh` and `bin/bindings.properties` from the local repo so the `jdbc-array-json` binding is recognized.
- Backups were created under `/home/ubuntu/ycsb_harness_backup_20260527T151546Z` and `/home/ubuntu/ycsb_harness_backup_20260527T151655Z_bin`.

Launch verification:

- tmux session `ycsb` was relaunched for `run3` at about `2026-05-27T15:40Z` UTC.
- Full-visibility prerequisites passed for both `full_view_prewarm_toast_index` and `full_view_prewarm_toast_index_unchange`.
- Main load phase completed with `10000` inserts and exit `0`.
- Epoch 1 extend completed with `100000` operations and exit `0`.
- Vacuum ran after epoch 1 and produced verbose heap plus TOAST vacuum output.
- `pg_prewarm` recorded TOAST-index-only intervention: relation role `toast_index`, relation `pg_toast_938380364_index`, `blocks_done=239`, status `ok`.
- Epoch 1 read/run phase completed with exit `0`.
- Run directory contains manifest, config, heartbeat, stdout/stderr, `pg_settings.csv`, `preflight.json`, sample CSVs, phase snapshots, and YCSB output.
- `logs/observability_errors.log` and `logs/sampler_errors.log` were empty at the first verification check.

Failure/fix notes:

- `run1` and `run2` both exited after epoch 1 extend, before vacuum/prewarm.
- The root cause was instrumentation, not the benchmark workload: phase metadata tried to read optional `fieldlength=` from the workload file while the heavy extend workload only had `extendfieldlength=`.
- Because `set -euo pipefail` was active outside the YCSB wrapper, the missing optional key caused an immediate exit.
- The harness was patched locally and deployed to the instance so metadata now falls back to `extendfieldlength` and treats missing optional fields as empty metadata, not fatal benchmark errors.
- The checkpoint-log observer was also hardened to return success when no new checkpoint log messages are found.

## Decisions

Treat `run3` as the active remote run, not completed evidence. Do not analyze the result until it has:

- final `exit_status.txt`
- `derived/summary.md`
- `derived/phase_deltas.csv`
- `derived/normalized_metrics.csv`
- populated `*_pg_prewarm.csv` showing TOAST-index-only intervention rows
- local pullback and artifact validation

## Next Actions

- Monitor disk space on `16.176.19.144`; launch-time free space was adequate but not luxurious.
- After completion, compress the run directory on the remote host before pulling it into `YCSB-IVS-DATA`.
- Compare Heavy NOVACC, Heavy VACC, heap plus TOAST-index prewarm, and TOAST-index-only prewarm once all artifacts are local.
