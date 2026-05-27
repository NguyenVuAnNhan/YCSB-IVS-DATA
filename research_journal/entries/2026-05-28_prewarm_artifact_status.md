# pg_prewarm Artifact Status

- Date: 2026-05-28
- Workspace: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`
- Related repo: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`
- Status: draft

## Context

This note records the artifact status for the pg_prewarm intervention thread so it does not get confused with completed, analyzable results.

The harness has pg_prewarm support, and the experiment design remains relevant:

- first intervention: warm the TOAST index only
- second intervention, if needed: warm heap plus TOAST index

## Notes

I did not find a completed local pg_prewarm benchrun artifact in `YCSB-IVS-DATA` during the first backfill pass.

Local searches found pg_prewarm support in the harness and disabled pg_prewarm metadata in the completed NOVACC run:

- `pg_prewarm_enabled=0`
- `pg_prewarm_mode=toast_index`

No local result directory with an enabled pg_prewarm intervention was found under the known result roots.

Follow-up remote checks with the correct EC2 user show that the pg_prewarm run is real and active, not merely planned:

- Host: `3.104.54.25`
- Login user: `ubuntu`
- Run ID: `full_view_heavy_prewarm_heap_toast_index_run1`
- Remote run directory: `/home/ubuntu/ycsb-ec2-bundle/experiment_scripts/benchruns/full_view_heavy_prewarm_heap_toast_index_run1`
- Remote tmux session: `ycsb`
- Manifest start: `2026-05-26T10:32:59Z`
- Status at check time `2026-05-27T15:08Z`: still running, around `reference_97`; no final `exit_status.txt` yet.
- Configuration evidence from manifest: `pg_prewarm_enabled=1`, `pg_prewarm_mode=heap_toast_index`, `scale=heavy`, `type=full_view_prewarm_heap_toast_index`, `work=pure`.
- Intervention evidence: `/home/ubuntu/ycsb-ec2-bundle/analysis/Data/Internal_data/toast_spike_trigger/full_view_prewarm_heap_toast_index_run1_zipfian_heavy_pure_pg_prewarm.csv` had `195` lines at the check, consistent with a header plus heap and TOAST-index prewarm rows through epoch `97`.
- Late-run prewarm rows show both `heap` and `toast_index` status `ok`; at epoch `97`, heap warmed `5685` blocks and TOAST index warmed `90316` blocks.

This means pg_prewarm should be treated as an active evidence-producing experiment, but not yet as a completed local artifact. The intervention being tested is heap plus TOAST index, not full TOAST heap prewarm.

## Decisions

Do not analyze or cite final pg_prewarm results until a completed run directory is pulled locally and checked for:

- `manifest.json`
- `config_resolved.json`
- `exit_status.txt`
- `logs/toast_spike_trigger/*_pg_prewarm.csv`
- phase snapshots containing `prewarm_start` and `prewarm_end`
- derived `phase_deltas.csv` and `normalized_metrics.csv`

## Next Actions

- Monitor `3.104.54.25` until `exit_status.txt` appears.
- Pull the completed benchrun directory, preferably compressed before transfer.
- Backfill a proper completed-run journal entry only after the artifacts are local.
